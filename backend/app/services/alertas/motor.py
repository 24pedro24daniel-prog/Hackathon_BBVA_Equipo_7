"""B10/B11 — Motor de alertas. Escribe la tabla `alertas` (es de B) y `preferencias_alertas`.

- Qué reglas corren según el disparador (lo pasa /ingesta/confirmar, PLAN §4.3):
    compra_credito → faltante_caja + pedido_excesivo · retiro_personal → retiro_excesivo + faltante_caja ·
    otros egresos → faltante_caja · ingresos → ninguna (más plata no crea un faltante) ·
    None / "consulta" (GET /alertas, POST /alertas/evaluar) → las 4.
- Sin duplicar: no se crea una alerta si ya hay una activa con la misma clave (tipo + entidad, y para el faltante
  también la fecha del evento). En la evaluación por consulta, tampoco si esa misma clave ya se atendió/descartó
  (si no, descartar no serviría: el GET la volvería a crear); un movimiento nuevo sí puede volver a levantarla.
- Límite diario y horario silencioso (preferencias, por defecto 2/día y 21:00–07:00): toda alerta nueva se guarda; se
  marca enviada (`enviada_en`) solo si no es horario silencioso y no se pasó el máximo del día; si no, queda con
  `enviada_en = null` (pendiente de notificar). Se evalúan por prioridad, así las 2 del día son las más importantes.
- Los textos (título, insight…) no se guardan: se arman al leer desde los campos de la fila (render).
- Nunca incluyen enlaces que pidan credenciales.
"""

from datetime import date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import reloj
from app.core.errors import NoEncontrado, Validacion
from app.core.ids import nuevo_id
from app.db import models as m
from app.schemas.alertas import (
    AccionAlertaRequest,
    AccionAlertaResponse,
    AccionAlertaSugerida,
    Alerta,
    AlertasResponse,
    Causa,
    PreferenciasAlertas,
)
from app.schemas.common import PRIORIDAD_ALERTA, CanalNotificacion, EstadoAlerta, TipoAlerta, TipoMovimiento
from app.services.alertas import reglas as r
from app.services.finanzas import consultas as q
from app.services.finanzas import proyeccion as fc
from app.services.finanzas.modelo_ml import meta_b, motivo_fallback_forecast
from app.services.ingesta.texto import fecha_corta, soles

VERSION = "0.1.0"
MODELO = f"reglas-alertas + {fc.MODELO}"
DISPARADOR_COMPRA_CREDITO = "compra_credito"
DISPARADOR_CONSULTA = "consulta"
A = TipoAlerta
TODAS = (A.faltante_caja, A.pedido_excesivo, A.retiro_excesivo, A.obligacion_proxima)
EGRESOS = {t.value for t in TipoMovimiento} - {t.value for t in (TipoMovimiento.venta, TipoMovimiento.cobro_fiado,
                                                                   TipoMovimiento.prestamo_recibido,
                                                                   TipoMovimiento.otro_ingreso)}  # fmt: skip
DIAS_SEMANA = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MICRO = {
    A.faltante_caja: "Si sacas de la caja sin un monto fijo, es difícil saber cuánto puedes pedir.",
    A.pedido_excesivo: "Pedir más de lo que vendes antes de pagar deja la plata atrapada en mercadería.",
    A.retiro_excesivo: "Un sueldo fijo para ti ayuda a que la caja del negocio no se quede corta.",
    A.obligacion_proxima: "Separar hoy la plata de un pago que se viene evita sorpresas ese día.",
}
ACCIONES = {
    "abrir_simulador": "Ver qué puedo hacer",
    "ver_retiros": "Ver mis retiros",
    "ver_cuentas": "Ver mis pagos",
}
# Textos de causas guardados por versiones anteriores (las causas se guardan en la fila): se muestran con el texto nuevo.
CAUSAS_ANTERIORES = {"Sacaste más para la casa": r.CAUSA_RETIROS,
                     "Retiros para la casa este mes": "Lo que sacaste de la caja este mes"}  # fmt: skip
ESTADO_POR_ACCION = {"ejecutada": ("atendida", EstadoAlerta.atendida), "descartada": ("descartada", EstadoAlerta.descartada),
                     "posponer": ("pospuesta", EstadoAlerta.activa)}  # fmt: skip


def reglas_para(disparador: str | None) -> tuple[TipoAlerta, ...]:
    if disparador in (None, "", DISPARADOR_CONSULTA):
        return TODAS
    if disparador == DISPARADOR_COMPRA_CREDITO:
        return (A.faltante_caja, A.pedido_excesivo)
    if disparador == TipoMovimiento.retiro_personal.value:
        return (A.faltante_caja, A.retiro_excesivo)
    if disparador in EGRESOS:
        return (A.faltante_caja,)
    return ()


def clave(tipo, entidad_id: str | None, fecha_evento: date | None) -> tuple:
    tipo = TipoAlerta(tipo)
    return (tipo.value, entidad_id, fecha_evento if tipo == A.faltante_caja else None)


# ── preferencias (B11) ──────────────────────────────────────────────────────────────────────────


def _hora(texto: str, campo: str) -> time:
    try:
        return time.fromisoformat(texto)
    except ValueError as exc:
        raise Validacion(f"La hora de '{campo}' no es válida (usa HH:MM).", [{"campo": campo, "problema": "HH:MM"}]) from exc


def preferencias(db: Session, empresa_id: str) -> m.PreferenciasAlertas:
    prefs = db.get(m.PreferenciasAlertas, empresa_id)
    return prefs or m.PreferenciasAlertas(empresa_id=empresa_id, canales=["whatsapp"], max_por_dia=2,
                                          silencio_desde=time(21, 0), silencio_hasta=time(7, 0), resumen_semanal=True)  # fmt: skip


def guardar_preferencias(db: Session, empresa_id: str, prefs: PreferenciasAlertas) -> PreferenciasAlertas:
    q.empresa_o_404(db, empresa_id)
    validos = {c.value for c in CanalNotificacion}
    malos = [c for c in prefs.canales if c not in validos]
    if malos or not prefs.canales:
        raise Validacion("Canal de alertas no válido.", [{"campo": "canales", "problema": f"usa {sorted(validos)}"}])
    fila = db.get(m.PreferenciasAlertas, empresa_id) or m.PreferenciasAlertas(empresa_id=empresa_id)
    fila.canales = list(dict.fromkeys(prefs.canales))
    fila.max_por_dia = prefs.max_por_dia
    fila.silencio_desde = _hora(prefs.silencio_desde, "silencio_desde")
    fila.silencio_hasta = _hora(prefs.silencio_hasta, "silencio_hasta")
    fila.resumen_semanal = prefs.resumen_semanal
    db.add(fila)
    db.commit()
    return _prefs_schema(fila)


def _prefs_schema(fila: m.PreferenciasAlertas) -> PreferenciasAlertas:
    return PreferenciasAlertas(canales=list(fila.canales), max_por_dia=fila.max_por_dia,
                               silencio_desde=fila.silencio_desde.strftime("%H:%M"),
                               silencio_hasta=fila.silencio_hasta.strftime("%H:%M"), resumen_semanal=fila.resumen_semanal)  # fmt: skip


def en_silencio(ahora: time, desde: time, hasta: time) -> bool:
    if desde == hasta:
        return False
    if desde < hasta:
        return desde <= ahora < hasta
    return ahora >= desde or ahora < hasta


# ── render ──────────────────────────────────────────────────────────────────────────────────────


def _dia(d: date, corte: date) -> str:
    dias = (d - corte).days
    if dias == 0:
        return "hoy"
    if dias == 1:
        return "mañana"
    if 1 < dias <= 6:
        return f"el {DIAS_SEMANA[d.weekday()]}"
    return f"el {fecha_corta(d)}"


def _textos(db: Session, fila: m.Alerta, corte: date) -> dict:
    tipo = TipoAlerta(fila.tipo)
    monto = Decimal(fila.monto or 0)
    deuda = db.get(m.Deuda, fila.entidad_id) if fila.entidad_tipo == "deuda" and fila.entidad_id else None
    nombre = None
    if deuda is not None:
        prov = db.get(m.Proveedor, deuda.proveedor_id) if deuda.proveedor_id else None
        nombre = prov.nombre_ficticio if prov else (deuda.acreedor_nombre or "tu prestamista")
    fecha = fecha_corta(fila.fecha_evento)
    if tipo == A.faltante_caja:
        if deuda is not None:
            titulo = f"El {fecha} te faltarían {soles(monto)} para pagar a {nombre}"
            insight = f"Para pagar {soles(deuda.monto_total_a_pagar)} a {nombre} te faltarían {soles(monto)}."
        else:
            titulo = f"El {fecha} te faltarían {soles(monto)} en la caja"
            insight = f"Si no cambias nada, el {fecha} tu caja quedaría en {soles(-monto)}."
        return {"titulo": titulo, "titulo_corto": f"El {fecha} no te alcanzará", "insight": insight}
    if tipo == A.pedido_excesivo:
        pedido = soles(deuda.monto_total_a_pagar) if deuda is not None else "este pedido"
        return {"titulo": f"Este pedido es {soles(monto)} más de lo que vendes hasta el {fecha}",
                "titulo_corto": "Pedido más grande que tus ventas",
                "insight": f"Pediste {pedido} a {nombre or 'tu proveedor'} y hasta el {fecha} sueles vender "
                           f"{soles(Decimal(str(fila.causas[1]['monto'])) if fila.causas else 0)} de eso."}  # fmt: skip
    if tipo == A.retiro_excesivo:
        total = Decimal(str(fila.causas[0]["monto"])) if fila.causas else monto
        return {"titulo": f"Con tus retiros ya sacaste {soles(total)} este mes",
                "titulo_corto": "Sacaste más de tu sueldo",
                "insight": f"Es {soles(monto)} más de lo que te tocaba a esta altura del mes."}
    cuando = _dia(fila.fecha_evento, corte)
    if fila.entidad_tipo == "impuesto":
        imp = db.get(m.Impuesto, fila.entidad_id)
        concepto = q.ImpuestoCalc(imp, False, "pendiente").nombre if imp else "impuesto"
        titulo = f"Tu {concepto} vence {cuando}"
    else:
        titulo = f"{cuando.capitalize()} vence tu pago a {nombre or 'tu acreedor'}"
    return {"titulo": titulo, "titulo_corto": "Pago que se viene", "insight": f"Son {soles(monto)}. Sepáralos desde hoy."}


def render(db: Session, fila: m.Alerta, prefs: m.PreferenciasAlertas | None = None, corte: date | None = None) -> Alerta:
    corte = corte or reloj.hoy()
    prefs = prefs or preferencias(db, fila.empresa_id)
    tipo = TipoAlerta(fila.tipo)
    causas = [Causa(descripcion=CAUSAS_ANTERIORES.get(c["descripcion"], c["descripcion"]), monto=Decimal(str(c["monto"])))
              for c in (fila.causas or [])]  # fmt: skip
    payload = {"pedido_id": fila.entidad_id} if fila.entidad_tipo == "deuda" else {}
    if fila.entidad_tipo == "impuesto":
        payload = {"impuesto_id": fila.entidad_id}
    textos = _textos(db, fila, corte)
    resumen = None
    if tipo == A.faltante_caja and causas:
        cortas = {r.CAUSA_RETIROS: "sacaste más de la caja de lo usual", r.CAUSA_PEDIDO: "pedido grande", r.CAUSA_FIADOS: "fiados sin cobrar"}
        partes = [cortas.get(c.descripcion, c.descripcion.lower()) for c in causas]
        resumen = (", ".join(partes[:-1]) + " y " + partes[-1] if len(partes) > 1 else partes[0]) + "."
    return Alerta(
        alerta_id=fila.alerta_id, tipo=tipo, prioridad=fila.prioridad, creada_en=reloj.a_lima(fila.creada_en),
        fecha_evento=fila.fecha_evento, dias_para_evento=(fila.fecha_evento - corte).days, monto=fila.monto,
        probabilidad=float(fila.probabilidad) if fila.probabilidad is not None else None, nivel_riesgo=fila.nivel_riesgo,
        resumen_causas=resumen, causas=causas,
        accion=AccionAlertaSugerida(tipo=fila.accion_sugerida or "abrir_simulador",
                                    texto_boton=ACCIONES.get(fila.accion_sugerida or "", "Ver qué puedo hacer"),
                                    payload=payload),
        microexplicacion=MICRO.get(tipo), canales=list(dict.fromkeys([*prefs.canales, "app"])),
        estado=EstadoAlerta(fila.estado).value, enviada_en=reloj.a_lima(fila.enviada_en) if fila.enviada_en else None,
        meta=meta_b(MODELO, VERSION, fallback=True, motivo=motivo_fallback_forecast()), **textos,
    )  # fmt: skip


# ── evaluación ──────────────────────────────────────────────────────────────────────────────────


def _enviadas_hoy(db: Session, empresa_id: str, ahora: datetime) -> int:
    inicio = reloj.inicio_del_dia(ahora.date())
    return db.scalar(select(func.count()).select_from(m.Alerta).where(
        m.Alerta.empresa_id == empresa_id, m.Alerta.enviada_en >= inicio,
        m.Alerta.enviada_en < inicio + timedelta(days=1))) or 0  # fmt: skip


def evaluar_alertas(db: Session, empresa_id: str, disparador: str | None = None, entidad_id: str | None = None,
                    fecha_corte: date | None = None) -> list[Alerta]:  # fmt: skip
    """Evalúa las reglas, guarda las alertas nuevas y las devuelve (ordenadas por prioridad)."""
    tipos = reglas_para(disparador)
    if not tipos:
        return []
    corte = q.corte_de(fecha_corte)
    ctx = r.Contexto(db, empresa_id, corte, disparador, entidad_id)
    q.empresa_o_404(db, empresa_id)
    candidatas = [c for t in tipos for c in r.REGLAS[t](ctx)]
    if not candidatas:
        return []
    candidatas.sort(key=lambda c: PRIORIDAD_ALERTA[c.tipo])
    existentes = db.scalars(select(m.Alerta).where(m.Alerta.empresa_id == empresa_id)).all()
    por_consulta = disparador in (None, "", DISPARADOR_CONSULTA)
    bloqueadas = {clave(a.tipo, a.entidad_id, a.fecha_evento) for a in existentes
                  if a.estado == EstadoAlerta.activa or por_consulta}  # fmt: skip
    prefs = preferencias(db, empresa_id)
    ahora = reloj.a_lima(reloj.ahora())
    silencio = en_silencio(ahora.time().replace(tzinfo=None), prefs.silencio_desde, prefs.silencio_hasta)
    enviadas = _enviadas_hoy(db, empresa_id, ahora)
    canal = next((c for c in prefs.canales if c in {x.value for x in CanalNotificacion}), CanalNotificacion.app.value)
    nuevas = []
    for c in candidatas:
        k = clave(c.tipo, c.entidad_id, c.fecha_evento)
        if k in bloqueadas:
            continue
        enviar = not silencio and enviadas < prefs.max_por_dia
        enviadas += int(enviar)
        fila = m.Alerta(alerta_id=nuevo_id(db, m.Alerta, "ALR"), empresa_id=empresa_id, tipo=c.tipo,
                        prioridad=PRIORIDAD_ALERTA[c.tipo], fecha_evento=c.fecha_evento, monto=c.monto,
                        probabilidad=Decimal(str(c.probabilidad)) if c.probabilidad is not None else None,
                        nivel_riesgo=c.nivel, causas=c.causas, accion_sugerida=c.accion, entidad_tipo=c.entidad_tipo,
                        entidad_id=c.entidad_id, canal=canal, estado=EstadoAlerta.activa, creada_en=ahora,
                        enviada_en=ahora if enviar else None, modelo_version=VERSION)  # fmt: skip
        db.add(fila)
        db.flush()
        bloqueadas.add(k)
        nuevas.append(fila)
    db.commit()
    return [render(db, f, prefs, corte) for f in nuevas]


def refrescar_tras_anulacion(db: Session, empresa_id: str, entidad_id: str) -> None:
    """Tras anular una cuenta: se descartan sus alertas activas y los faltantes activos se recalculan con la proyección
    nueva (si el faltante ya no existe, se cierra; si cambió, se actualizan monto y causas). No hace commit."""
    activas = db.scalars(select(m.Alerta).where(m.Alerta.empresa_id == empresa_id,
                                                m.Alerta.estado == EstadoAlerta.activa)).all()  # fmt: skip
    if not activas:
        return
    ahora = reloj.ahora()
    faltantes = {}
    for c in r.faltante_caja(r.Contexto(db, empresa_id, reloj.hoy())):
        faltantes[clave(c.tipo, c.entidad_id, c.fecha_evento)] = c
    for fila in activas:
        k = clave(fila.tipo, fila.entidad_id, fila.fecha_evento)
        if fila.entidad_id == entidad_id or (fila.tipo == A.faltante_caja and k not in faltantes):
            fila.estado = EstadoAlerta.descartada
            fila.accion_tomada = "cuenta_anulada"
            fila.fecha_accion = ahora
        elif fila.tipo == A.faltante_caja:
            c = faltantes[k]
            fila.monto, fila.causas, fila.nivel_riesgo = c.monto, c.causas, c.nivel
            fila.probabilidad = Decimal(str(c.probabilidad)) if c.probabilidad is not None else None
    db.flush()


def alertas(db: Session, empresa_id: str, estado: str = "activa") -> AlertasResponse:
    """Lista de alertas. Con estado = activa primero evalúa (sin duplicar), así el inicio muestra el faltante del día."""
    q.empresa_o_404(db, empresa_id)
    if estado == EstadoAlerta.activa.value:
        evaluar_alertas(db, empresa_id, DISPARADOR_CONSULTA)
    consulta = select(m.Alerta).where(m.Alerta.empresa_id == empresa_id)
    if estado not in ("todas", ""):
        try:
            consulta = consulta.where(m.Alerta.estado == EstadoAlerta(estado))
        except ValueError as exc:
            raise Validacion("Estado de alerta no válido.", [{"campo": "estado", "problema": "activa|atendida|descartada"}]) from exc
    filas = db.scalars(consulta.order_by(m.Alerta.prioridad, m.Alerta.creada_en.desc(), m.Alerta.alerta_id)).all()
    prefs = preferencias(db, empresa_id)
    corte = reloj.hoy()
    return AlertasResponse(items=[render(db, f, prefs, corte) for f in filas])


def registrar_accion(db: Session, alerta_id: str, req: AccionAlertaRequest) -> AccionAlertaResponse:
    fila = db.get(m.Alerta, alerta_id) if db is not None else None
    if fila is None:
        raise NoEncontrado("No encontré esa alerta.")
    respuesta, estado = ESTADO_POR_ACCION[req.accion]
    fila.estado = estado
    fila.accion_tomada = (f"{req.accion}: {req.detalle}" if req.detalle else req.accion)[:50]
    fila.fecha_accion = reloj.ahora()
    if req.accion == "posponer":
        fila.enviada_en = None  # se vuelve a notificar más adelante
    db.commit()
    return AccionAlertaResponse(estado=respuesta)

"""B10/B11 — Motor de alertas. Escribe la tabla `alertas` (es de B) y `preferencias_alertas`.

- Qué reglas corren según el disparador (lo pasa /ingesta/confirmar, PLAN §4.3):
    compra_credito → faltante_caja + pedido_excesivo · retiro_personal → faltante_caja + retiro_excesivo ·
    compra / gasto_negocio → faltante_caja + gasto_inusual · otros pagos → faltante_caja · cobro_fiado → fiado_vencido ·
    otros ingresos → solo se refrescan las alertas que ya existen (más plata no crea un faltante) ·
    None / "consulta" (POST /alertas/evaluar) → todas.
- Persistencia: los GET (`alertas()`) NO escriben. Calculan las alertas vigentes al momento: las ya guardadas con su
  monto/causas al día y las que todavía no se guardaron, marcadas `persistida = false` con un `alerta_id` estable
  (`ALR-PEND.<empresa>.<tipo>.<entidad>.<fecha>`). Se guardan en `POST /alertas/evaluar`, en el flujo de confirmar
  (§4.3) o al tocar una acción sobre una alerta pendiente (`POST /alertas/{id}/accion`).
- Al reevaluar, la alerta activa de la misma entidad se actualiza (monto, causas, nivel, probabilidad) y la que ya no
  aplica se cierra (`descartada`, `accion_tomada = ya_no_aplica`). Una alerta atendida/descartada por el usuario no se
  vuelve a crear en la evaluación por consulta; un movimiento nuevo sí puede volver a levantarla.
- Sin duplicar: no se crea una alerta si ya hay una activa con la misma clave (tipo + entidad, y para el faltante y el
  gasto inusual también la fecha del evento).
- Límite diario y horario silencioso (preferencias, por defecto 2/día y 21:00–07:00): toda alerta nueva se guarda; se
  marca enviada (`enviada_en`) solo si no es horario silencioso y no se pasó el máximo del día; si no, queda con
  `enviada_en = null` (pendiente de notificar). Se evalúan por prioridad, así las 2 del día son las más importantes.
- Los textos (título, insight…) no se guardan: se arman al leer desde los campos de la fila (render), para los 9 tipos.
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
from app.services.finanzas.modelo_ml import meta_b, motor_forecast
from app.services.ingesta.texto import fecha_corta, soles

VERSION = "0.2.0"
MODELO = f"reglas-alertas + {fc.MODELO}"


def _meta_alerta():
    """`meta` de una alerta: reglas + el motor de forecast vigente (LightGBM o baseline con su motivo)."""
    motor = motor_forecast()
    return meta_b(f"reglas-alertas + {motor.modelo}", VERSION, fallback=motor.fallback, motivo=motor.motivo)


DISPARADOR_COMPRA_CREDITO = "compra_credito"
DISPARADOR_CONSULTA = "consulta"
A = TipoAlerta
T = TipoMovimiento
TODAS = (A.faltante_caja, A.pedido_excesivo, A.retiro_excesivo, A.obligacion_proxima, A.gasto_inusual, A.fiado_vencido,
         A.meta_lograda)  # fmt: skip
INGRESOS = {t.value for t in (T.venta, T.cobro_fiado, T.prestamo_recibido, T.otro_ingreso)}
EGRESOS = {t.value for t in T} - INGRESOS
GASTOS_DE_RUTINA = {T.compra.value, T.gasto_negocio.value}
DIAS_SEMANA = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MICRO = {
    A.faltante_caja: "Si sacas de la caja sin un monto fijo, es difícil saber cuánto puedes pedir.",
    A.pedido_excesivo: "Pedir más de lo que vendes antes de pagar deja la plata atrapada en mercadería.",
    A.retiro_excesivo: "Un sueldo fijo para ti ayuda a que la caja del negocio no se quede corta.",
    A.obligacion_proxima: "Separar hoy la plata de un pago que se viene evita sorpresas ese día.",
    A.gasto_inusual: "Mirar en qué se fue la plata de hoy ayuda a saber si fue un gasto único o se va a repetir.",
    A.fiado_vencido: "Recordar a tiempo, con cariño, es la forma más fácil de cobrar un fiado.",
    A.meta_lograda: "Cada meta lograda es un hábito que ya tienes; sigue con la siguiente.",
    A.caida_ventas: "Cuando las ventas bajan unos días, conviene revisar el horario y que no falte mercadería.",
    A.resumen_semanal: "Ver tu semana completa te ayuda a decidir con calma la siguiente.",
}
ACCIONES = {
    "abrir_simulador": "Ver qué puedo hacer",
    "ver_retiros": "Ver mis retiros",
    "ver_cuentas": "Ver mis pagos",
    "recordar_cliente": "Recordar al cliente",
    "ver_movimientos": "Ver mis movimientos",
    "ver_progreso": "Ver mi progreso",
    "ver_forecast": "Ver mis próximos 30 días",
}
ACCION_POR_TIPO = {A.faltante_caja: "abrir_simulador", A.pedido_excesivo: "abrir_simulador",
                   A.retiro_excesivo: "ver_retiros", A.obligacion_proxima: "ver_cuentas",
                   A.gasto_inusual: "ver_movimientos", A.fiado_vencido: "recordar_cliente",
                   A.meta_lograda: "ver_progreso", A.caida_ventas: "ver_forecast",
                   A.resumen_semanal: "ver_forecast"}  # fmt: skip
# Textos de causas guardados por versiones anteriores (las causas se guardan en la fila): se muestran con el texto nuevo.
CAUSAS_ANTERIORES = {"Sacaste más para la casa": r.CAUSA_RETIROS,
                     "Retiros para la casa este mes": "Lo que sacaste de la caja este mes"}  # fmt: skip
ESTADO_POR_ACCION = {"ejecutada": ("atendida", EstadoAlerta.atendida), "descartada": ("descartada", EstadoAlerta.descartada),
                     "posponer": ("pospuesta", EstadoAlerta.activa)}  # fmt: skip
YA_NO_APLICA = "ya_no_aplica"  # cierre automático: no cuenta como "el usuario la descartó"
PREFIJO_PENDIENTE = "ALR-PEND"


def reglas_para(disparador: str | None) -> tuple[TipoAlerta, ...]:
    if es_consulta(disparador):
        return TODAS
    if disparador == DISPARADOR_COMPRA_CREDITO:
        return (A.faltante_caja, A.pedido_excesivo)
    if disparador == T.retiro_personal.value:
        return (A.faltante_caja, A.retiro_excesivo)
    if disparador in GASTOS_DE_RUTINA:
        return (A.faltante_caja, A.gasto_inusual)
    if disparador in EGRESOS:
        return (A.faltante_caja,)
    if disparador == T.cobro_fiado.value:
        return (A.faltante_caja, A.fiado_vencido)
    if disparador in INGRESOS:
        return (A.faltante_caja,)
    return ()


def es_consulta(disparador: str | None) -> bool:
    return disparador in (None, "", DISPARADOR_CONSULTA)


def solo_refresca(disparador: str | None) -> bool:
    """Un ingreso no crea alertas (más plata no crea un faltante): solo actualiza o cierra las que ya existen."""
    return disparador in INGRESOS


def clave(tipo, entidad_id: str | None, fecha_evento: date | None) -> tuple:
    """Identidad de una alerta. El faltante se distingue además por fecha; el gasto inusual es uno por día."""
    tipo = TipoAlerta(tipo)
    if tipo == A.gasto_inusual:
        return (tipo.value, None, fecha_evento)
    return (tipo.value, entidad_id, fecha_evento if tipo == A.faltante_caja else None)


def clave_de(x) -> tuple:
    """Clave de una fila `alertas` o de una candidata (misma forma)."""
    return clave(x.tipo, x.entidad_id, x.fecha_evento)


def _cerrable(tipo: TipoAlerta, completa: bool) -> bool:
    """Una evaluación parcial (disparada por un pedido) no prueba que otros pedidos ya no excedan."""
    return completa or tipo != A.pedido_excesivo


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
    if dias == -1:
        return "ayer"
    if 1 < dias <= 6:
        return f"el {DIAS_SEMANA[d.weekday()]}"
    return f"el {fecha_corta(d)}"


def _causas(fila: m.Alerta) -> list[dict]:
    """Causas como [{descripcion, monto}], tolerando el formato antiguo {causa, impacto}. Nunca asume cuántas hay."""
    salida = []
    for c in fila.causas or []:
        if not isinstance(c, dict):
            continue
        descripcion = c.get("descripcion") or c.get("causa")
        valor = c.get("monto", c.get("impacto"))
        if descripcion is None or valor is None:
            continue
        try:
            salida.append({"descripcion": CAUSAS_ANTERIORES.get(str(descripcion), str(descripcion)),
                           "monto": Decimal(str(valor))})
        except ArithmeticError:
            continue
    return salida


def _monto_causa(causas: list[dict], i: int) -> Decimal | None:
    return causas[i]["monto"] if len(causas) > i else None


def _entidad(fila: m.Alerta) -> str | None:
    return r.entidad_canonica(fila.entidad_tipo)


def _nombre_acreedor(db: Session, deuda: m.Deuda) -> str:
    prov = db.get(m.Proveedor, deuda.proveedor_id) if deuda.proveedor_id else None
    return prov.nombre_ficticio if prov else (deuda.acreedor_nombre or "tu prestamista")


def _textos(db: Session, fila: m.Alerta, corte: date, causas: list[dict]) -> dict:
    tipo = TipoAlerta(fila.tipo)
    monto = Decimal(fila.monto or 0)
    entidad = _entidad(fila)
    deuda = db.get(m.Deuda, fila.entidad_id) if entidad == "deudas" and fila.entidad_id else None
    nombre = _nombre_acreedor(db, deuda) if deuda is not None else None
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
        venta = _monto_causa(causas, 1)
        insight = (f"Pediste {pedido} a {nombre or 'tu proveedor'} y hasta el {fecha} sueles vender {soles(venta)} de eso."
                   if venta is not None else
                   f"Pediste {pedido} a {nombre or 'tu proveedor'} y es más de lo que sueles vender de eso hasta el {fecha}.")
        return {"titulo": f"Este pedido es {soles(monto)} más de lo que vendes hasta el {fecha}",
                "titulo_corto": "Pedido más grande que tus ventas", "insight": insight}
    if tipo == A.retiro_excesivo:
        total = _monto_causa(causas, 0) if entidad == "mes" else None
        titulo = (f"Con tus retiros ya sacaste {soles(total)} este mes" if total is not None
                  else f"Sacaste {soles(monto)} más de lo que te tocaba este mes")
        return {"titulo": titulo, "titulo_corto": "Sacaste más de tu sueldo",
                "insight": f"Es {soles(monto)} más de lo que te tocaba a esta altura del mes."}
    if tipo == A.obligacion_proxima:
        cuando = _dia(fila.fecha_evento, corte)
        if entidad == "impuestos":
            imp = db.get(m.Impuesto, fila.entidad_id) if fila.entidad_id else None
            concepto = q.ImpuestoCalc(imp, False, "pendiente").nombre if imp else "impuesto"
            titulo = f"Tu {concepto} vence {cuando}"
        else:
            titulo = f"{cuando.capitalize()} vence tu pago a {nombre or 'tu acreedor'}"
        return {"titulo": titulo, "titulo_corto": "Pago que se viene", "insight": f"Son {soles(monto)}. Sepáralos desde hoy."}
    if tipo == A.gasto_inusual:
        cuando = _dia(fila.fecha_evento, corte)
        total, usual = _monto_causa(causas, 0), _monto_causa(causas, 1)
        insight = (f"Entre compras y gastos del negocio salieron {soles(total)} {cuando}; un día normal salen {soles(usual)}."
                   if total is not None and usual is not None else
                   f"Salió más plata {cuando} de la que sale en un día normal.")
        return {"titulo": f"{cuando.capitalize()} gastaste {soles(monto)} más de lo usual",
                "titulo_corto": "Gasto más alto de lo usual", "insight": insight}
    if tipo == A.fiado_vencido:
        fiado = db.get(m.CuadernoFiado, fila.entidad_id) if entidad == "cuaderno_fiado" and fila.entidad_id else None
        cliente = db.get(m.Cliente, fiado.cliente_id) if fiado is not None else None
        quien = cliente.nombre_ficticio if cliente else "Un cliente"
        dias = f" Hace {(corte - fiado.fecha_fiado).days} días que le fiaste." if fiado is not None and corte >= fiado.fecha_fiado else ""
        return {"titulo": f"{quien} te debe {soles(monto)} y ya pasó la fecha",
                "titulo_corto": "Fiado vencido",
                "insight": f"Son {soles(monto)} de fiados vencidos.{dias} Un recordatorio amable ayuda a cobrarlos."}
    if tipo == A.meta_lograda:
        meta = db.get(m.ReglaMeta, fila.entidad_id) if entidad == "reglas_meta" and fila.entidad_id else None
        from app.services.salud.metas import TITULOS

        nombre_meta = TITULOS.get(meta.plantilla.value) if meta is not None else None
        titulo = f"¡Lograste tu meta: {nombre_meta.lower()}!" if nombre_meta else "¡Lograste tu meta!"
        return {"titulo": titulo, "titulo_corto": "Meta lograda",
                "insight": "Lo que llevas ya llegó a tu objetivo. Cuando quieras, te ayudo a ponerte la siguiente."}
    if tipo == A.caida_ventas:
        return {"titulo": "Tus ventas vienen más bajas de lo usual", "titulo_corto": "Ventas más bajas",
                "insight": "Revisa si cambió tu horario o si te faltó mercadería esos días."}
    return {"titulo": "Tu resumen de la semana", "titulo_corto": "Resumen de la semana",
            "insight": "Mira cómo te fue esta semana y qué se viene para decidir con calma."}


def _accion(db: Session, fila: m.Alerta) -> AccionAlertaSugerida:
    tipo = TipoAlerta(fila.tipo)
    accion = fila.accion_sugerida if fila.accion_sugerida in ACCIONES else ACCION_POR_TIPO[tipo]
    entidad = _entidad(fila)
    payload: dict = {}
    if entidad == "deudas" and fila.entidad_id:
        payload = {"pedido_id": fila.entidad_id}
    elif entidad == "impuestos" and fila.entidad_id:
        payload = {"impuesto_id": fila.entidad_id}
    elif entidad == "cuaderno_fiado" and fila.entidad_id:
        fiado = db.get(m.CuadernoFiado, fila.entidad_id)
        payload = {"fiado_id": fila.entidad_id, **({"cliente_id": fiado.cliente_id} if fiado is not None else {})}
    if accion == "ver_movimientos" and tipo == A.gasto_inusual:
        payload = {"tipo": T.gasto_negocio.value}
    return AccionAlertaSugerida(tipo=accion, texto_boton=ACCIONES[accion], payload=payload)


def render(db: Session, fila: m.Alerta, prefs: m.PreferenciasAlertas | None = None, corte: date | None = None,
           persistida: bool = True) -> Alerta:  # fmt: skip
    corte = corte or reloj.hoy()
    prefs = prefs or preferencias(db, fila.empresa_id)
    tipo = TipoAlerta(fila.tipo)
    lista = _causas(fila)
    causas = [Causa(descripcion=c["descripcion"], monto=c["monto"]) for c in lista]
    textos = _textos(db, fila, corte, lista)
    resumen = None
    if tipo == A.faltante_caja and causas:
        cortas = {r.CAUSA_RETIROS: "sacaste más de la caja de lo usual", r.CAUSA_PEDIDO: "pedido grande", r.CAUSA_FIADOS: "fiados sin cobrar"}
        partes = [cortas.get(c.descripcion, c.descripcion.lower()) for c in causas]
        resumen = (", ".join(partes[:-1]) + " y " + partes[-1] if len(partes) > 1 else partes[0]) + "."
    return Alerta(
        alerta_id=fila.alerta_id, tipo=tipo, prioridad=fila.prioridad, creada_en=reloj.a_lima(fila.creada_en),
        fecha_evento=fila.fecha_evento, dias_para_evento=(fila.fecha_evento - corte).days, monto=fila.monto,
        probabilidad=float(fila.probabilidad) if fila.probabilidad is not None else None, nivel_riesgo=fila.nivel_riesgo,
        resumen_causas=resumen, causas=causas, accion=_accion(db, fila),
        microexplicacion=MICRO.get(tipo), canales=list(dict.fromkeys([*prefs.canales, "app"])),
        estado=EstadoAlerta(fila.estado).value, enviada_en=reloj.a_lima(fila.enviada_en) if fila.enviada_en else None,
        persistida=persistida,
        meta=_meta_alerta(), **textos,
    )  # fmt: skip


# ── evaluación ──────────────────────────────────────────────────────────────────────────────────


def _enviadas_hoy(db: Session, empresa_id: str, ahora: datetime) -> int:
    inicio = reloj.inicio_del_dia(ahora.date())
    return db.scalar(select(func.count()).select_from(m.Alerta).where(
        m.Alerta.empresa_id == empresa_id, m.Alerta.enviada_en >= inicio,
        m.Alerta.enviada_en < inicio + timedelta(days=1))) or 0  # fmt: skip


def _prob(c: r.Candidata) -> Decimal | None:
    return Decimal(str(c.probabilidad)) if c.probabilidad is not None else None


def _canal(prefs: m.PreferenciasAlertas) -> str:
    return next((c for c in prefs.canales if c in {x.value for x in CanalNotificacion}), CanalNotificacion.app.value)


def _actualizar(fila: m.Alerta, c: r.Candidata) -> None:
    """La alerta activa de la misma entidad se pone al día con lo que dice el cálculo de ahora."""
    fila.monto, fila.causas, fila.nivel_riesgo, fila.probabilidad = c.monto, c.causas, c.nivel, _prob(c)
    fila.entidad_tipo, fila.entidad_id, fila.accion_sugerida = c.entidad_tipo, c.entidad_id, c.accion
    fila.fecha_evento = c.fecha_evento


def _fila_nueva(c: r.Candidata, empresa_id: str, canal: str, ahora: datetime, alerta_id: str,
                enviada: bool = False) -> m.Alerta:  # fmt: skip
    return m.Alerta(alerta_id=alerta_id, empresa_id=empresa_id, tipo=c.tipo, prioridad=PRIORIDAD_ALERTA[c.tipo],
                    fecha_evento=c.fecha_evento, monto=c.monto, probabilidad=_prob(c), nivel_riesgo=c.nivel,
                    causas=c.causas, accion_sugerida=c.accion, entidad_tipo=c.entidad_tipo, entidad_id=c.entidad_id,
                    canal=canal, estado=EstadoAlerta.activa, creada_en=ahora, enviada_en=ahora if enviada else None,
                    modelo_version=VERSION)  # fmt: skip


def _cerrar(fila: m.Alerta, ahora: datetime) -> None:
    fila.estado, fila.accion_tomada, fila.fecha_accion = EstadoAlerta.descartada, YA_NO_APLICA, ahora


def _candidatas(ctx: r.Contexto, tipos) -> list[r.Candidata]:
    candidatas = [c for t in tipos for c in r.REGLAS[t](ctx)]
    candidatas.sort(key=lambda c: PRIORIDAD_ALERTA[c.tipo])
    return candidatas


def _bloqueantes(existentes: list[m.Alerta], por_consulta: bool) -> set[tuple]:
    """Claves que impiden crear otra alerta: las activas siempre; en la evaluación por consulta también las que el
    usuario ya atendió o descartó (si no, descartar no serviría). Un cierre automático no bloquea."""
    return {clave_de(a) for a in existentes
            if a.estado == EstadoAlerta.activa or (por_consulta and a.accion_tomada != YA_NO_APLICA)}  # fmt: skip


def evaluar_alertas(db: Session, empresa_id: str, disparador: str | None = None, entidad_id: str | None = None,
                    fecha_corte: date | None = None) -> list[Alerta]:  # fmt: skip
    """Evalúa las reglas, guarda las alertas nuevas, pone al día las activas y devuelve las nuevas (por prioridad)."""
    tipos = reglas_para(disparador)
    if not tipos:
        return []
    corte = q.corte_de(fecha_corte)
    q.empresa_o_404(db, empresa_id)
    ctx = r.Contexto(db, empresa_id, corte, disparador, entidad_id)
    completa = es_consulta(disparador)
    candidatas = _candidatas(ctx, tipos)
    por_clave = {clave_de(c): c for c in candidatas}
    existentes = db.scalars(select(m.Alerta).where(m.Alerta.empresa_id == empresa_id)
                            .order_by(m.Alerta.creada_en, m.Alerta.alerta_id)).all()  # fmt: skip
    ahora = reloj.a_lima(reloj.ahora())
    # 1) las activas de las reglas evaluadas se ponen al día o se cierran si ya no aplican
    for fila in existentes:
        tipo = TipoAlerta(fila.tipo)
        if fila.estado != EstadoAlerta.activa or tipo not in tipos:
            continue
        c = por_clave.get(clave_de(fila))
        if c is not None:
            _actualizar(fila, c)
        elif _cerrable(tipo, completa):
            _cerrar(fila, ahora)
    nuevas: list[m.Alerta] = []
    if not solo_refresca(disparador):
        bloqueadas = _bloqueantes(existentes, completa)
        prefs = preferencias(db, empresa_id)
        silencio = en_silencio(ahora.time().replace(tzinfo=None), prefs.silencio_desde, prefs.silencio_hasta)
        enviadas = _enviadas_hoy(db, empresa_id, ahora)
        for c in candidatas:
            k = clave_de(c)
            if k in bloqueadas:
                continue
            enviar = not silencio and enviadas < prefs.max_por_dia
            enviadas += int(enviar)
            fila = _fila_nueva(c, empresa_id, _canal(prefs), ahora, nuevo_id(db, m.Alerta, "ALR"), enviar)
            db.add(fila)
            db.flush()
            bloqueadas.add(k)
            nuevas.append(fila)
    db.commit()
    prefs = preferencias(db, empresa_id)
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
        faltantes[clave_de(c)] = c
    for fila in activas:
        k = clave_de(fila)
        if fila.entidad_id == entidad_id or (fila.tipo == A.faltante_caja and k not in faltantes):
            fila.estado = EstadoAlerta.descartada
            fila.accion_tomada = "cuenta_anulada"
            fila.fecha_accion = ahora
        elif fila.tipo == A.faltante_caja:
            c = faltantes[k]
            fila.monto, fila.causas, fila.nivel_riesgo = c.monto, c.causas, c.nivel
            fila.probabilidad = _prob(c)
    db.flush()


# ── lectura (sin escribir) ──────────────────────────────────────────────────────────────────────


def id_pendiente(empresa_id: str, c: r.Candidata) -> str:
    """ID estable de una alerta vigente que todavía no se guardó: se arma con su clave (sin escribir nada)."""
    tipo, entidad, fecha = clave_de(c)
    return ".".join([PREFIJO_PENDIENTE, empresa_id, tipo, entidad or "-", fecha.isoformat() if fecha else "-"])


def _clave_de_id(alerta_id: str) -> tuple[str, tuple]:
    partes = alerta_id.split(".")
    if len(partes) != 5 or partes[0] != PREFIJO_PENDIENTE:
        raise NoEncontrado("No encontré esa alerta.")
    _, empresa_id, tipo, entidad, fecha = partes
    try:
        k = clave(tipo, None if entidad == "-" else entidad, date.fromisoformat(fecha) if fecha != "-" else None)
    except ValueError as exc:
        raise NoEncontrado("No encontré esa alerta.") from exc
    return empresa_id, k


def _vigentes(db: Session, empresa_id: str, corte: date):
    """(candidatas por clave, existentes) de la evaluación completa, sin escribir."""
    ctx = r.Contexto(db, empresa_id, corte, None, None)
    candidatas = _candidatas(ctx, TODAS)
    existentes = db.scalars(select(m.Alerta).where(m.Alerta.empresa_id == empresa_id)).all()
    return candidatas, existentes


def _con_valores_de_hoy(fila: m.Alerta, c: r.Candidata) -> m.Alerta:
    """Copia de la fila (no gestionada por la sesión) con los valores del cálculo de ahora; la fila real no se toca."""
    nueva = _fila_nueva(c, fila.empresa_id, fila.canal, fila.creada_en, fila.alerta_id, False)
    nueva.estado, nueva.enviada_en, nueva.prioridad = fila.estado, fila.enviada_en, fila.prioridad
    return nueva


def alertas(db: Session, empresa_id: str, estado: str = "activa") -> AlertasResponse:
    """Lista de alertas SIN escribir en la BD. Con estado = activa (o todas) calcula las vigentes al momento: las ya
    guardadas con su monto y causas al día más las que todavía no se guardaron (`persistida = false`)."""
    q.empresa_o_404(db, empresa_id)
    estados = {e.value for e in EstadoAlerta}
    if estado not in estados | {"todas", ""}:
        raise Validacion("Estado de alerta no válido.", [{"campo": "estado", "problema": "activa|atendida|descartada|todas"}])
    prefs = preferencias(db, empresa_id)
    corte = reloj.hoy()
    items: list[tuple[tuple, Alerta]] = []
    filas = db.scalars(select(m.Alerta).where(m.Alerta.empresa_id == empresa_id)).all()
    if estado in (EstadoAlerta.activa.value, "todas", ""):
        candidatas = _candidatas(r.Contexto(db, empresa_id, corte, None, None), TODAS)
        por_clave = {clave_de(c): c for c in candidatas}
        activas = {}
        for f in sorted(filas, key=lambda f: (f.creada_en, f.alerta_id)):
            if f.estado == EstadoAlerta.activa:
                activas.setdefault(clave_de(f), f)
        ocupadas = {clave_de(f) for f in filas if f.accion_tomada != YA_NO_APLICA}
        ahora = reloj.a_lima(reloj.ahora())
        canal = _canal(prefs)
        for f in filas:
            if f.estado != EstadoAlerta.activa:
                continue
            k = clave_de(f)
            if TipoAlerta(f.tipo) not in TODAS:  # caida_ventas, resumen_semanal: sin regla propia, se muestran como están
                items.append(((f.prioridad, -f.creada_en.timestamp(), f.alerta_id), render(db, f, prefs, corte)))
            elif activas.get(k) is f and k in por_clave:
                items.append(((f.prioridad, -f.creada_en.timestamp(), f.alerta_id),
                              render(db, _con_valores_de_hoy(f, por_clave[k]), prefs, corte)))
        for c in candidatas:
            k = clave_de(c)
            if k in ocupadas:
                continue
            fila = _fila_nueva(c, empresa_id, canal, ahora, id_pendiente(empresa_id, c), False)
            items.append(((fila.prioridad, -ahora.timestamp(), fila.alerta_id), render(db, fila, prefs, corte, False)))
        if estado in ("todas", ""):
            for f in filas:
                if f.estado != EstadoAlerta.activa:
                    items.append(((f.prioridad, -f.creada_en.timestamp(), f.alerta_id), render(db, f, prefs, corte)))
    else:
        for f in filas:
            if f.estado == EstadoAlerta(estado):
                items.append(((f.prioridad, -f.creada_en.timestamp(), f.alerta_id), render(db, f, prefs, corte)))
    items.sort(key=lambda x: x[0])
    return AlertasResponse(items=[a for _, a in items])


# ── acciones ────────────────────────────────────────────────────────────────────────────────────


def _guardar_pendiente(db: Session, alerta_id: str) -> m.Alerta:
    """Convierte una alerta vigente no guardada en fila (al tocar una acción sobre ella)."""
    empresa_id, k = _clave_de_id(alerta_id)
    q.empresa_o_404(db, empresa_id)
    corte = reloj.hoy()
    candidatas, existentes = _vigentes(db, empresa_id, corte)
    for f in existentes:  # ya la guardó otra evaluación: se usa esa
        if f.estado == EstadoAlerta.activa and clave_de(f) == k:
            return f
    c = next((c for c in candidatas if clave_de(c) == k), None)
    if c is None:
        raise NoEncontrado("Esa alerta ya no está vigente.")
    prefs = preferencias(db, empresa_id)
    ahora = reloj.a_lima(reloj.ahora())
    fila = _fila_nueva(c, empresa_id, _canal(prefs), ahora, nuevo_id(db, m.Alerta, "ALR"), False)
    db.add(fila)
    db.flush()
    return fila


def registrar_accion(db: Session, alerta_id: str, req: AccionAlertaRequest) -> AccionAlertaResponse:
    if db is None:
        raise NoEncontrado("No encontré esa alerta.")
    fila = db.get(m.Alerta, alerta_id)
    if fila is None and alerta_id.startswith(PREFIJO_PENDIENTE + "."):
        fila = _guardar_pendiente(db, alerta_id)
    if fila is None:
        raise NoEncontrado("No encontré esa alerta.")
    respuesta, estado = ESTADO_POR_ACCION[req.accion]
    fila.estado = estado
    fila.accion_tomada = (f"{req.accion}: {req.detalle}" if req.detalle else req.accion)[:50]
    fila.fecha_accion = reloj.ahora()
    if req.accion == "posponer":
        fila.enviada_en = None  # se vuelve a notificar más adelante
    db.commit()
    return AccionAlertaResponse(estado=respuesta, alerta_id=fila.alerta_id)

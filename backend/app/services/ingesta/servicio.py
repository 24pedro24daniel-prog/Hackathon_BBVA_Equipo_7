"""Flujos de ingesta (A3–A6, A11): interpretar → (aclarar) → confirmar → registrar → motores de B.

Los routers (`/ingesta/*`, `/movimientos`) y el webhook de WhatsApp usan estas funciones, así el chat simulado y
la app siguen exactamente el mismo camino. Tras guardar se llama a B según PLAN_MVP.md §4.3.
"""

import logging
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.core.config import settings
from app.core.errors import Conflicto, NoEncontrado, NoInterpretable, ServicioNoDisponible, Validacion
from app.core.ids import nuevo_id
from app.core.meta import construir_meta
from app.core.reloj import ahora, zona
from app.db import models as m
from app.schemas.common import Canal, Dinero, EstadoBorrador, MetodoPago, TipoMovimiento
from app.schemas.ingesta import (
    ConfirmarRequest,
    ConfirmarResponse,
    InterpretarRequest,
    MovimientoBorrador,
    MovimientoPropuesto,
    RegistroResultado,
)
from app.services import alertas as motor_alertas
from app.services import finanzas
from app.services.ingesta import catalogo as cat_mod
from app.services.ingesta import cuaderno as cuaderno_mod
from app.services.ingesta import extractor, idempotencia, registrador, transcriptor
from app.services.ingesta.texto import fecha_corta, soles

log = logging.getLogger("cajaclara.ingesta")

ENDPOINT_CONFIRMAR = "POST /ingesta/confirmar"
ENDPOINT_MOVIMIENTO = "POST /empresas/{id}/movimientos"
T = TipoMovimiento


def empresa_o_404(db, empresa_id: str) -> m.Empresa:
    empresa = db.get(m.Empresa, empresa_id)
    if empresa is None:
        raise NoEncontrado("No encontré esa empresa.")
    return empresa


def _modelo_whisper() -> str:
    return f"whisper-{settings.WHISPER_MODEL}"


# ── interpretar ─────────────────────────────────────────────────────────────────────────────────


def _transcribir(req: InterpretarRequest) -> tuple[str, str | None, bool, bool]:
    """(texto a interpretar, transcripción, ¿usó Whisper?, ¿hubo fallback de voz?)."""
    if req.canal != Canal.voz:
        if not (req.texto and req.texto.strip()):
            raise Validacion("Envía el texto del mensaje.", [{"campo": "texto", "problema": "obligatorio"}])
        return req.texto, None, False, False
    try:
        escuchado = transcriptor.transcribir_media(req.media_url, req.empresa_id)
    except transcriptor.TranscriptorNoDisponible as exc:
        log.warning("Whisper no disponible: %s", exc)
        if not (req.texto and req.texto.strip()):
            raise ServicioNoDisponible("Ahora no puedo escuchar audios. ¿Me lo escribes, por favor?") from exc
        return req.texto, req.texto, False, True
    if escuchado is None:
        if req.texto and req.texto.strip():
            return req.texto, req.texto, False, False
        raise NoInterpretable("No encontré el audio. ¿Me lo mandas otra vez o me lo escribes?",
                              [{"campo": "media_url", "problema": "archivo no encontrado"}])  # fmt: skip
    if not escuchado.strip():
        raise NoInterpretable("No se escuchó nada en el audio. ¿Me lo repites?")
    return escuchado, escuchado, True, False


def chequeo_para(db, empresa_id: str, mov: dict, opciones: list[dict] | None = None) -> dict | None:
    """Chequeo antes del pedido (B, §4.5) para una compra a crédito; None si no aplica o B falla."""
    if mov.get("tipo") != T.compra.value or mov.get("metodo_pago") != MetodoPago.credito.value or not mov.get("monto"):
        return None
    fecha = mov.get("fecha_vencimiento") or (opciones[0]["valor"] if opciones else None)
    if not fecha:
        return None
    try:
        r = finanzas.chequeo_pedido(db, empresa_id, mov.get("contraparte") or "", Decimal(str(mov["monto"])),
                                    date.fromisoformat(str(fecha)))  # fmt: skip
        return {**r.model_dump(mode="json"), "fecha_vencimiento": str(fecha)}
    except Exception:  # noqa: BLE001 - el chequeo no debe impedir registrar
        log.exception("chequeo_pedido falló")
        return None


def interpretar(db, req: InterpretarRequest) -> dict:
    empresa_o_404(db, req.empresa_id)
    if req.canal == Canal.foto:
        raise Validacion("Para la foto del cuaderno usa /ingesta/cuaderno.", [{"campo": "canal", "problema": "foto"}])
    texto, transcripcion, uso_whisper, fallback_voz = _transcribir(req)
    ext = extractor.extraer(texto, empresa_id=req.empresa_id, db=db)
    mov = MovimientoBorrador.model_validate(ext.movimiento).model_dump(mode="json")

    borrador = m.Borrador(
        borrador_id=nuevo_id(db, m.Borrador, "BOR"), empresa_id=req.empresa_id, canal=req.canal,
        media_url=req.media_url, texto_original=texto, payload_propuesto=mov, origen_monto=ext.origen_monto,
        confianza=Decimal(str(ext.confianza)), campos_faltantes=ext.campos_faltantes or None,
        pregunta_aclaratoria=ext.pregunta_aclaratoria, estado=EstadoBorrador.pendiente,
        modelo_version=ext.modelo_version[:30], prompt_version=extractor.PROMPT_VERSION if not ext.fallback_usado else None,
        fallback_usado=ext.fallback_usado or fallback_voz, creado_en=ahora(),
    )  # fmt: skip
    db.add(borrador)
    db.commit()

    modelo = f"{_modelo_whisper()} + {ext.modelo}" if uso_whisper else ext.modelo
    respuesta: dict[str, Any] = {
        "borrador_id": borrador.borrador_id,
        "transcripcion": transcripcion,
        "movimiento_propuesto": mov,
        "origen_monto": ext.origen_monto.value,
        "confianza": ext.confianza,
        "campos_faltantes": ext.campos_faltantes,
        "pregunta_aclaratoria": ext.pregunta_aclaratoria,
        "meta": construir_meta(modelo, ext.modelo_version, prompt_version=extractor.PROMPT_VERSION,
                               fallback_usado=ext.fallback_usado or fallback_voz).model_dump(mode="json"),  # fmt: skip
    }
    if ext.opciones_aclaracion:
        respuesta["opciones_aclaracion"] = ext.opciones_aclaracion
    if ext.fuera_de_alcance:
        respuesta["fuera_de_alcance"] = True
    if chequeo := chequeo_para(db, req.empresa_id, mov, ext.opciones_aclaracion):
        respuesta["chequeo_pedido"] = chequeo
    return respuesta


# ── confirmar ───────────────────────────────────────────────────────────────────────────────────

_CAMPOS_CORREGIBLES = set(MovimientoPropuesto.model_fields) | {"salio_de_caja", "fiados"}


def _es_no(valor) -> bool:
    return valor is False or (isinstance(valor, str) and valor.strip().lower() in ("no", "false", "0"))


def aplicar_correcciones(payload: dict, correcciones: dict) -> MovimientoPropuesto:
    desconocidos = sorted(set(correcciones) - _CAMPOS_CORREGIBLES)
    if desconocidos:
        raise Validacion(f"No puedo corregir el campo '{desconocidos[0]}'.",
                         [{"campo": c, "problema": "campo desconocido"} for c in desconocidos])  # fmt: skip
    final = {k: v for k, v in payload.items() if k in MovimientoPropuesto.model_fields}
    cambios = {k: v for k, v in correcciones.items() if k in MovimientoPropuesto.model_fields}
    final.update(cambios)
    if "tipo" in cambios and final["tipo"] not in (T.venta.value, T.compra.value):
        final["items"] = []
    if "monto" in cambios and final.get("items"):
        items = final["items"]
        if len(items) == 1:
            monto = Decimal(str(final["monto"]))
            cantidad = Decimal(str(items[0]["cantidad"]))
            items[0] = {**items[0], "precio_unitario": str(round(monto / cantidad, 2)), "subtotal": str(monto)}
        else:
            final["items"] = []
    try:
        return MovimientoPropuesto.model_validate(final)
    except ValidationError as exc:
        detalles = [{"campo": ".".join(str(p) for p in e["loc"]) or "payload", "problema": e["msg"]} for e in exc.errors()]
        if any(d["campo"] == "monto" for d in detalles):
            raise Validacion("Falta el monto: dime cuánto fue.", detalles) from exc
        raise Validacion(f"El campo '{detalles[0]['campo']}' no es válido: {detalles[0]['problema']}.", detalles) from exc


def despues_de_registrar(db, empresa_id: str, mov: MovimientoPropuesto | None, res: RegistroResultado,
                         disparador: str | None = None) -> dict:  # fmt: skip
    """Llamadas a B tras guardar (PLAN §4.3): chequeo si es pedido a crédito, alertas y saldo de caja."""
    chequeo = None
    entidad = res.movimiento_id
    if mov is None:
        pass
    elif mov.tipo == T.compra.value and mov.metodo_pago == MetodoPago.credito.value:
        deuda_id = next((r.id for r in res.registros_creados if r.tabla == "deudas"), None)
        deuda = db.get(m.Deuda, deuda_id) if deuda_id else None
        disparador, entidad = "compra_credito", deuda_id
        if deuda is not None:
            chequeo = chequeo_para(db, empresa_id, {**mov.model_dump(mode="json"),
                                                    "fecha_vencimiento": deuda.fecha_vencimiento.isoformat()})  # fmt: skip
    else:
        disparador = mov.tipo
    try:
        nuevas = motor_alertas.evaluar_alertas(db, empresa_id, disparador=disparador, entidad_id=entidad)
        alertas = [a.model_dump(mode="json") for a in nuevas]
    except Exception:  # noqa: BLE001 - el registro ya está guardado; las alertas no deben tumbarlo
        log.exception("evaluar_alertas falló")
        alertas = []
    saldo = finanzas.saldo_caja(db, empresa_id)
    cuerpo = ConfirmarResponse(movimiento_id=res.movimiento_id, registros_creados=res.registros_creados,
                               alertas_disparadas=alertas, saldo_caja_negocio=saldo).model_dump(mode="json")  # fmt: skip
    if chequeo:
        cuerpo["chequeo_pedido"] = chequeo
    return cuerpo


class _FiadoConfirmado(BaseModel):
    model_config = ConfigDict(extra="ignore")
    cliente: str = Field(min_length=1, max_length=100)
    detalle: str | None = Field(default=None, max_length=255)
    monto: Dinero = Field(gt=0)
    fecha: date


def _confirmar_cuaderno(db, borrador: m.Borrador, correcciones: dict) -> tuple[RegistroResultado, list[dict]]:
    crudos = correcciones.get("fiados", borrador.payload_propuesto.get("fiados", []))
    try:
        fiados = [_FiadoConfirmado.model_validate(f) for f in crudos]
    except ValidationError as exc:
        raise Validacion("Revisa los fiados: cada uno necesita cliente, monto y fecha.",
                         [{"campo": "fiados", "problema": e["msg"]} for e in exc.errors()]) from exc  # fmt: skip
    if not fiados:
        raise Validacion("No hay fiados para guardar.", [{"campo": "fiados", "problema": "vacío"}])
    cat = cat_mod.cargar(db, borrador.empresa_id)
    creados, duplicados, primero = [], [], None
    for f in fiados:
        cli = cat.buscar_cliente(f.cliente)
        if cli is not None:
            existente = db.query(m.CuadernoFiado).filter_by(empresa_id=borrador.empresa_id, cliente_id=cli.cliente_id,
                                                           monto=f.monto, fecha_fiado=f.fecha).first()  # fmt: skip
            if existente is not None:
                duplicados.append({"cliente": cli.nombre, "monto": float(f.monto), "fecha": f.fecha.isoformat(),
                                   "fiado_id": existente.fiado_id})  # fmt: skip
                continue
        mov = MovimientoPropuesto(tipo=T.venta, monto=f.monto, metodo_pago=MetodoPago.credito,
                                  contraparte=cli.nombre if cli else f.cliente, descripcion=f.detalle,
                                  fecha_hora=datetime.combine(f.fecha, time(12, 0), tzinfo=zona()))  # fmt: skip
        res = registrador.registrar_movimiento(db, borrador.empresa_id, mov, canal=Canal.foto,
                                               borrador_id=borrador.borrador_id, confianza=borrador.confianza,
                                               fue_corregida="fiados" in correcciones, commit=False)  # fmt: skip
        primero = primero or res.movimiento_id
        creados += res.registros_creados
        cat = cat_mod.cargar(db, borrador.empresa_id)
    if primero is None:
        tx = db.query(m.Transaccion).filter_by(fiado_id=duplicados[0]["fiado_id"], tipo=T.venta).first()
        primero = tx.transaccion_id if tx else duplicados[0]["fiado_id"]
    return RegistroResultado(movimiento_id=primero, registros_creados=creados), duplicados


def confirmar(db, req: ConfirmarRequest, idempotency_key: str | None = None) -> tuple[int, dict | None]:
    payload_idem = req.model_dump(mode="json")
    if guardada := idempotencia.buscar_respuesta(db, idempotency_key, ENDPOINT_CONFIRMAR, payload_idem):
        return guardada.status_code, guardada.respuesta
    borrador = db.get(m.Borrador, req.borrador_id)
    if borrador is None:
        raise NoEncontrado("Ese registro ya no existe. Vuelve a enviarlo.")
    if borrador.estado == EstadoBorrador.confirmado:
        raise Conflicto("Ese registro ya fue confirmado.")
    if borrador.estado == EstadoBorrador.descartado:
        raise Conflicto("Ese registro ya fue descartado.")

    correcciones = {k: v for k, v in (req.correcciones or {}).items() if not str(k).startswith("_")}
    if (not req.confirmado and not correcciones) or _es_no(correcciones.get("salio_de_caja", True)):
        borrador.estado, borrador.resuelto_en = EstadoBorrador.descartado, ahora()
        borrador.correcciones = correcciones or None
        db.commit()
        idempotencia.guardar_respuesta(db, idempotency_key, ENDPOINT_CONFIRMAR, payload_idem, 204, None,
                                       borrador.empresa_id)  # fmt: skip
        return 204, None

    duplicados: list[dict] = []
    es_cuaderno = borrador.canal == Canal.foto and "fiados" in borrador.payload_propuesto
    mov_ref = None if es_cuaderno else aplicar_correcciones(borrador.payload_propuesto, correcciones)
    borrador.estado, borrador.resuelto_en = EstadoBorrador.confirmado, ahora()
    borrador.correcciones = correcciones or None
    if es_cuaderno:
        try:
            res, duplicados = _confirmar_cuaderno(db, borrador, correcciones)
            db.commit()
        except Exception:
            db.rollback()
            raise
        cuerpo = despues_de_registrar(db, borrador.empresa_id, None, res, disparador="cuaderno")
    else:
        res = registrador.registrar_movimiento(db, borrador.empresa_id, mov_ref, canal=borrador.canal,
                                               borrador_id=borrador.borrador_id, confianza=borrador.confianza,
                                               fue_corregida=bool(correcciones))  # fmt: skip
        cuerpo = despues_de_registrar(db, borrador.empresa_id, mov_ref, res)
    if duplicados:
        cuerpo["duplicados"] = duplicados
    idempotencia.guardar_respuesta(db, idempotency_key, ENDPOINT_CONFIRMAR, payload_idem, 201, cuerpo,
                                   borrador.empresa_id)  # fmt: skip
    return 201, cuerpo


# ── registro manual (formulario web) ────────────────────────────────────────────────────────────


def registrar_manual(db, empresa_id: str, mov: MovimientoPropuesto, idempotency_key: str | None = None) -> dict:
    empresa_o_404(db, empresa_id)
    payload_idem = {"empresa_id": empresa_id, **mov.model_dump(mode="json")}
    if guardada := idempotencia.buscar_respuesta(db, idempotency_key, ENDPOINT_MOVIMIENTO, payload_idem):
        return guardada.respuesta
    mov = MovimientoPropuesto.model_validate(mov.model_dump())
    res = registrador.registrar_movimiento(db, empresa_id, mov, canal=Canal.manual)
    cuerpo = despues_de_registrar(db, empresa_id, mov, res)
    idempotencia.guardar_respuesta(db, idempotency_key, ENDPOINT_MOVIMIENTO, payload_idem, 201, cuerpo, empresa_id)
    return cuerpo


# ── cuaderno ────────────────────────────────────────────────────────────────────────────────────


def leer_cuaderno(db, empresa_id: str, media_url: str) -> dict:
    empresa_o_404(db, empresa_id)
    lectura = cuaderno_mod.leer_cuaderno(media_url, empresa_id=empresa_id, db=db)
    publicos = [{k: v for k, v in f.items()} for f in lectura.fiados]
    confianzas = [f["confianza"] for f in lectura.fiados]
    borrador = m.Borrador(
        borrador_id=nuevo_id(db, m.Borrador, "BOR"), empresa_id=empresa_id, canal=Canal.foto, media_url=media_url,
        payload_propuesto={"fiados": publicos, "lineas_no_legibles": lectura.lineas_no_legibles,
                           "lineas_tachadas": lectura.lineas_tachadas},
        confianza=Decimal(str(min(confianzas))) if confianzas else None, estado=EstadoBorrador.pendiente,
        modelo_version=lectura.modelo_version[:30], prompt_version=lectura.prompt_version,
        fallback_usado=lectura.fallback_usado, creado_en=ahora(),
    )  # fmt: skip
    db.add(borrador)
    db.commit()
    return {
        "borrador_id": borrador.borrador_id,
        "fiados_propuestos": publicos,
        "lineas_no_legibles": lectura.lineas_no_legibles,
        "lineas_tachadas": lectura.lineas_tachadas,
        "meta": construir_meta(lectura.modelo, lectura.modelo_version, prompt_version=lectura.prompt_version,
                               fallback_usado=lectura.fallback_usado).model_dump(mode="json"),  # fmt: skip
    }


# ── textos para el chat ─────────────────────────────────────────────────────────────────────────

_METODO_TXT = {"efectivo": "efectivo", "billetera_digital": "billetera", "transferencia": "transferencia",
               "tarjeta": "tarjeta", "credito": "a crédito"}  # fmt: skip
_TIPO_TXT = {"venta": "venta", "cobro_fiado": "cobro de fiado", "prestamo_recibido": "préstamo recibido",
             "otro_ingreso": "otro ingreso", "compra": "compra", "gasto_negocio": "gasto del negocio",
             "retiro_personal": "para la casa", "pago_proveedor": "pago a proveedor", "pago_prestamo": "pago de préstamo",
             "pago_impuesto": "impuesto"}  # fmt: skip


def _cantidad(valor) -> str:
    d = Decimal(str(valor)).normalize()
    return f"{d:f}"


def resumen_movimiento(mov: dict) -> str:
    """"2 cervezas, S/ 13.00, efectivo" · "pedido a crédito de S/ 2 400 a Distribuidora Andina"."""
    tipo, metodo = mov.get("tipo"), mov.get("metodo_pago")
    monto = soles(mov["monto"], True) if mov.get("monto") else "monto por confirmar"
    if tipo == "compra" and metodo == "credito":
        txt = f"pedido a crédito de {monto}"
        if mov.get("contraparte"):
            txt += f" a {mov['contraparte']}"
        if mov.get("fecha_vencimiento"):
            txt += f", lo pagas el {fecha_corta(date.fromisoformat(str(mov['fecha_vencimiento'])))}"
        return txt
    if tipo == "venta" and metodo == "credito":
        return f"fiado a {mov.get('contraparte') or 'un cliente'}, {monto}"
    partes = []
    if mov.get("items"):
        partes.append(", ".join(f"{_cantidad(i['cantidad'])} {i.get('producto') or 'producto'}" for i in mov["items"]))
    else:
        partes.append(_TIPO_TXT.get(tipo, tipo))
    if mov.get("contraparte") and tipo in ("cobro_fiado", "pago_proveedor", "prestamo_recibido", "pago_prestamo"):
        partes[-1] += f" ({mov['contraparte']})"
    partes.append(monto)
    if metodo:
        partes.append(_METODO_TXT.get(metodo, metodo))
    return ", ".join(partes)


def texto_chequeo(chequeo: dict) -> str:
    fecha = fecha_corta(date.fromisoformat(chequeo["fecha_vencimiento"])) if chequeo.get("fecha_vencimiento") else ""
    saldo = Decimal(str(chequeo["saldo_proyectado_al_vencimiento"]))
    if chequeo.get("estado_caja") == "te_alcanza":
        return f"Revisé tu caja: el {fecha} te alcanza (quedarías con {soles(saldo)})."
    lineas = [f"⚠ Ojo: si pagas ese pedido el {fecha}, ese día tu caja quedaría en {soles(saldo)}."]
    for s in chequeo.get("sugerencias", [])[:3]:
        resultado = soles(Decimal(str(s["saldo_resultante"])))
        if s["accion"] == "reducir_pedido" and s.get("monto_sugerido") is not None:
            lineas.append(f"• Pedir {soles(Decimal(str(s['monto_sugerido'])))}: quedarías con {resultado}.")
        elif s["accion"] == "pagar_en_partes":
            lineas.append(f"• Pagar en {s.get('partes') or 2} partes: quedarías con {resultado}.")
        elif s["accion"] == "combinar":
            lineas.append(f"• {(s.get('detalle') or 'Combinar').capitalize()}: quedarías con {resultado}.")
    return "\n".join(lineas)

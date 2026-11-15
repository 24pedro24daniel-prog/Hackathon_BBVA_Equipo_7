"""Chat de WhatsApp simulado (A7): enruta cada mensaje al flujo que toca y arma la respuesta con botones.

- La decisión de qué es cada texto (registro, corrección, confirmación, pregunta) la toma `enrutador.py`, la misma
  que usa el chat de la app (`POST /empresas/{id}/chat/mensajes`); aquí solo se arma el texto y los botones.
- texto/audio → interpretar (registro) · pregunta → asistente · imagen → cuaderno de fiados.
- Botones: `confirmar:BOR-x`, `corregir:BOR-x`, `descartar:BOR-x`, `opcion:BOR-x:campo=valor`.
- Tras "corregir" o una pregunta aclaratoria sin opciones, el siguiente texto se toma como la corrección.
- Reenvíos del proveedor: `mensaje_id` funciona como Idempotency-Key (misma respuesta, nada se duplica).
"""

import hashlib
from datetime import date
from decimal import Decimal

from sqlalchemy import select

from app.core.errors import ErrorAPI, NoEncontrado
from app.db import models as m
from app.schemas.common import Canal, EstadoBorrador
from app.schemas.ingesta import ConfirmarRequest, InterpretarRequest, WebhookRequest
from app.services.ingesta import enrutador, idempotencia, servicio
from app.services.ingesta.enrutador import EN_CORRECCION
from app.services.ingesta.servicio import resumen_movimiento, texto_chequeo
from app.services.ingesta.texto import fecha_corta, soles

ENDPOINT = "POST /webhooks/whatsapp"


def _botones_confirmar(borrador_id: str) -> list[dict]:
    return [{"id": f"confirmar:{borrador_id}", "texto": "✅ Correcto"},
            {"id": f"corregir:{borrador_id}", "texto": "✏️ Corregir"}]  # fmt: skip


def _respuesta(texto: str, botones: list[dict] | None = None) -> dict:
    return {"respuesta_texto": texto, "botones": botones or [], "respuesta_audio_url": None}


def enrutar_empresa(db, body: WebhookRequest) -> m.Empresa:
    if body.empresa_id:
        return servicio.empresa_o_404(db, body.empresa_id)
    clave = body.telefono_hash.lower()
    for empresa in db.scalars(select(m.Empresa)).all():
        digest = hashlib.sha256(empresa.telefono_whatsapp.encode()).hexdigest()
        if len(clave) >= 6 and digest.startswith(clave):
            return empresa
    raise NoEncontrado("No encontré un negocio asociado a ese número.")


def _texto_interpretacion(db, res: dict) -> dict:
    mov, bid = res["movimiento_propuesto"], res["borrador_id"]
    opciones = res.get("opciones_aclaracion") or []
    faltantes = res.get("campos_faltantes") or []
    if opciones:
        campo = faltantes[0] if faltantes else "fecha_vencimiento"
        botones = [{"id": f"opcion:{bid}:{campo}={o['valor']}", "texto": o["texto"]} for o in opciones]
        if campo == "salio_de_caja":
            return _respuesta(res["pregunta_aclaratoria"], botones)
        return _respuesta(f"Entendí: {resumen_movimiento(mov)}.\n{res['pregunta_aclaratoria']}", botones)
    if faltantes:
        borrador = db.get(m.Borrador, bid)
        enrutador.guardar_correcciones(db, borrador, {}, en_correccion=True)
        return _respuesta(f"Entendí: {resumen_movimiento(mov)}.\n{res['pregunta_aclaratoria']}",
                          [{"id": f"descartar:{bid}", "texto": "Descartar"}])  # fmt: skip
    texto = f"Anotado: {resumen_movimiento(mov)} ✅ ¿Correcto?"
    if res.get("pregunta_aclaratoria"):
        texto = f"Anotado: {resumen_movimiento(mov)}. {res['pregunta_aclaratoria']}"
    if chequeo := res.get("chequeo_pedido"):
        texto += "\n" + texto_chequeo(chequeo)
    return _respuesta(texto, _botones_confirmar(bid))


def _desde_resultado(db, r: enrutador.Resultado) -> dict:
    """Resultado del enrutador común → texto y botones de WhatsApp."""
    if r.tipo == "registro":
        respuesta = _texto_interpretacion(db, r.interpretacion)
        if r.transcripcion:
            respuesta["respuesta_texto"] = f"🎙️ «{r.transcripcion}»\n{respuesta['respuesta_texto']}"
        return respuesta
    if r.tipo == "borrador_actualizado":
        interp = r.interpretacion
        bid = interp["borrador_id"]
        if interp.get("campos_faltantes"):
            borrador = db.get(m.Borrador, bid)
            enrutador.guardar_correcciones(db, borrador, {}, en_correccion=True)
            return _respuesta(r.mensaje or interp["pregunta_aclaratoria"], [{"id": f"descartar:{bid}", "texto": "Descartar"}])
        texto = f"Corregido: {resumen_movimiento(interp['movimiento_propuesto'])} ✅ ¿Ahora sí?"
        if chequeo := interp.get("chequeo_pedido"):
            texto += "\n" + texto_chequeo(chequeo)
        return _respuesta(texto, _botones_confirmar(bid))
    if r.tipo == "guardado":
        return _respuesta(enrutador.texto_guardado(r.confirmacion or {}))
    if r.tipo == "descartado":
        return _respuesta(r.mensaje or "Listo, no lo anoté.")
    texto = r.mensaje or ""
    return _respuesta(f"🎙️ «{r.transcripcion}»\n{texto}" if r.transcripcion else texto)


def _boton(db, empresa: m.Empresa, valor: str) -> dict:
    accion, _, resto = (valor or "").partition(":")
    borrador_id, _, opcion = resto.partition(":")
    borrador = db.get(m.Borrador, borrador_id) if borrador_id else None
    if borrador is None or borrador.empresa_id != empresa.empresa_id:
        return _respuesta("Ese registro ya no está. ¿Me lo mandas otra vez?")
    if borrador.estado != EstadoBorrador.pendiente:
        return _respuesta("Ese registro ya estaba resuelto ✅")
    if accion == "confirmar":
        return _desde_resultado(db, enrutador.confirmar(db, borrador))
    if accion == "descartar":
        servicio.confirmar(db, ConfirmarRequest(borrador_id=borrador.borrador_id, confirmado=False))
        return _respuesta("Listo, no lo anoté.")
    if accion == "corregir":
        enrutador.guardar_correcciones(db, borrador, {}, en_correccion=True)
        return _respuesta("Ya, ¿qué le cambio? Por ejemplo: «fue por yape», «eran 15 soles» o «lo saqué de la caja».")
    if accion == "opcion":
        campo, _, dato = opcion.partition("=")
        if campo == "salio_de_caja":
            if dato == "no":
                servicio.confirmar(db, ConfirmarRequest(borrador_id=borrador.borrador_id, confirmado=False))
                return _respuesta("Ya, entonces no lo anoto: aquí solo va la plata del negocio.")
            return _desde_resultado(db, enrutador.confirmar(db, borrador))
        enrutador.guardar_correcciones(db, borrador, {campo: dato})
        mov = enrutador.mov_actual(borrador)
        texto = f"Anotado: {resumen_movimiento(mov)} ✅ ¿Correcto?"
        if campo == "fecha_vencimiento" and (chequeo := servicio.chequeo_para(db, empresa.empresa_id, mov)):
            texto += "\n" + texto_chequeo(chequeo)
        return _respuesta(texto, _botones_confirmar(borrador.borrador_id))
    return _respuesta("Ese botón ya no funciona. Cuéntame por aquí qué necesitas.")


def _en_correccion(db, empresa_id: str) -> m.Borrador | None:
    pendientes = db.scalars(select(m.Borrador).where(m.Borrador.empresa_id == empresa_id,
                                                     m.Borrador.estado == EstadoBorrador.pendiente)
                            .order_by(m.Borrador.creado_en.desc()).limit(5)).all()  # fmt: skip
    return next((b for b in pendientes if (b.correcciones or {}).get(EN_CORRECCION)), None)


def _cuaderno(db, empresa_id: str, media_url: str | None) -> dict:
    res = servicio.leer_cuaderno(db, empresa_id, media_url or "")
    fiados = res["fiados_propuestos"]
    if not fiados:
        return _respuesta("No encontré fiados en la foto. ¿Puedes tomarla más de cerca y con buena luz?")
    lineas = [f"Leí {len(fiados)} fiados:"]
    for f in fiados:
        lineas.append(f"• {f['cliente']}: {soles(Decimal(str(f['monto'])))} ({fecha_corta(date.fromisoformat(f['fecha']))})")
    if res["lineas_no_legibles"]:
        lineas.append(f"No pude leer {res['lineas_no_legibles']} línea(s).")
    lineas.append("¿Los guardo?")
    bid = res["borrador_id"]
    return _respuesta("\n".join(lineas), [{"id": f"confirmar:{bid}", "texto": "Sí, guardar"},
                                          {"id": f"descartar:{bid}", "texto": "No, descartar"}])  # fmt: skip


def procesar(db, body: WebhookRequest) -> dict:
    payload = body.model_dump(mode="json", exclude={"recibido_en"})
    if guardada := idempotencia.buscar_respuesta(db, body.mensaje_id, ENDPOINT, payload):
        return guardada.respuesta
    empresa = enrutar_empresa(db, body)
    try:
        if body.tipo == "boton":
            respuesta = _boton(db, empresa, body.texto or "")
        elif body.tipo == "imagen":
            respuesta = _cuaderno(db, empresa.empresa_id, body.media_url)
        elif body.tipo == "audio":
            # Se escucha primero: una pregunta por voz ("¿cómo va mi caja?") va al asistente; un movimiento, a registro.
            transcrito = servicio.transcribir(InterpretarRequest(empresa_id=empresa.empresa_id, canal=Canal.voz,
                                                                 texto=body.texto, media_url=body.media_url))  # fmt: skip
            r = enrutador.procesar_texto(db, empresa.empresa_id, transcrito[0], _en_correccion(db, empresa.empresa_id),
                                         canal_asistente="whatsapp", autoguardar=False, canal=Canal.voz,
                                         media_url=body.media_url, transcrito=transcrito)  # fmt: skip
            respuesta = _desde_resultado(db, r)
        elif not (body.texto or "").strip():
            respuesta = _respuesta("No me llegó nada 🙂 Cuéntame qué vendiste o gastaste, o pregúntame lo que quieras.")
        else:
            # Tras "Corregir" o una pregunta aclaratoria sin botones, el texto se cruza con ese borrador; si no tiene
            # que ver con él, se trata como mensaje nuevo. Sin borrador marcado, los botones confirman.
            r = enrutador.procesar_texto(db, empresa.empresa_id, body.texto, _en_correccion(db, empresa.empresa_id),
                                         canal_asistente="whatsapp", autoguardar=False)  # fmt: skip
            respuesta = _desde_resultado(db, r)
    except ErrorAPI as exc:
        respuesta = _respuesta(exc.mensaje)
    idempotencia.guardar_respuesta(db, body.mensaje_id, ENDPOINT, payload, 200, respuesta, empresa.empresa_id)
    return respuesta

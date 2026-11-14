"""Chat de WhatsApp simulado (A7): enruta cada mensaje al flujo que toca y arma la respuesta con botones.

- texto/audio → interpretar (registro) · pregunta → asistente · imagen → cuaderno de fiados.
- Botones: `confirmar:BOR-x`, `corregir:BOR-x`, `descartar:BOR-x`, `opcion:BOR-x:campo=valor`.
- Tras "corregir" o una pregunta aclaratoria sin opciones, el siguiente texto se toma como la corrección.
- Reenvíos del proveedor: `mensaje_id` funciona como Idempotency-Key (misma respuesta, nada se duplica).
"""

import hashlib
import re
from datetime import date
from decimal import Decimal

from sqlalchemy import select

from app.core.errors import ErrorAPI, NoEncontrado, NoInterpretable
from app.db import models as m
from app.schemas.common import Canal, EstadoBorrador
from app.schemas.ingesta import ConfirmarRequest, InterpretarRequest, WebhookRequest
from app.services.asistente import orquestador
from app.services.ingesta import idempotencia, servicio
from app.services.ingesta.servicio import aplicar_correcciones, resumen_movimiento, texto_chequeo
from app.services.ingesta.texto import fecha_corta, normalizar, numeros, soles

ENDPOINT = "POST /webhooks/whatsapp"
EN_CORRECCION = "_en_correccion"
_PREGUNTA = re.compile(r"\?|^¿|\bcomo va\b|\bpor que\b|\bprestamo\b|^y si\b|\bcuanto tengo\b|\bme alcanza\b|\bque hago\b|"
                       r"\bque es\b|\bayuda\b|^hola\b|^buen[oa]s\b")  # fmt: skip


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


def _correcciones(borrador: m.Borrador) -> dict:
    return {k: v for k, v in (borrador.correcciones or {}).items() if not k.startswith("_")}


def _guardar_correcciones(db, borrador: m.Borrador, nuevas: dict, en_correccion: bool = False) -> None:
    borrador.correcciones = {**_correcciones(borrador), **nuevas, EN_CORRECCION: en_correccion}
    db.commit()


def _mov_actual(borrador: m.Borrador) -> dict:
    return {**borrador.payload_propuesto, **_correcciones(borrador)}


def parsear_correccion(texto: str, campo: str | None = None) -> dict:
    """Texto libre → correcciones ("fue por billetera", "fueron 15", "era para la casa", "a Rosa")."""
    t = normalizar(texto)
    c: dict = {}
    if re.search(r"\b(billetera|yape|plin|digital)\b", t):
        c["metodo_pago"] = "billetera_digital"
    elif re.search(r"\b(efectivo|cash)\b", t):
        c["metodo_pago"] = "efectivo"
    elif re.search(r"\b(tarjeta|pos)\b", t):
        c["metodo_pago"] = "tarjeta"
    elif re.search(r"\btransferencia\b", t):
        c["metodo_pago"] = "transferencia"
    elif re.search(r"\b(fiado|credito)\b", t):
        c["metodo_pago"] = "credito"
    if re.search(r"\bpara la casa\b|\bpersonal\b", t):
        c["tipo"] = "retiro_personal"
    elif re.search(r"\bventa\b|\bvendi\b", t):
        c["tipo"] = "venta"
    cifras = [n for n in numeros(t) if n.texto not in ("un", "una", "uno")]
    if cifras and campo in (None, "monto"):
        c["monto"] = str(cifras[0].valor)
    if campo == "contraparte" and not c:
        nombre = re.sub(r"^(a|al|a la|el|la|fue|era|de)\s+", "", t).strip()
        if nombre:
            c["contraparte"] = nombre.title()[:100]
    return c


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
        _guardar_correcciones(db, borrador, {}, en_correccion=True)
        return _respuesta(f"Entendí: {resumen_movimiento(mov)}.\n{res['pregunta_aclaratoria']}",
                          [{"id": f"descartar:{bid}", "texto": "Descartar"}])  # fmt: skip
    texto = f"Anotado: {resumen_movimiento(mov)} ✅ ¿Correcto?"
    if res.get("pregunta_aclaratoria"):
        texto = f"Anotado: {resumen_movimiento(mov)}. {res['pregunta_aclaratoria']}"
    if chequeo := res.get("chequeo_pedido"):
        texto += "\n" + texto_chequeo(chequeo)
    return _respuesta(texto, _botones_confirmar(bid))


def _texto_confirmado(cuerpo: dict | None) -> str:
    if cuerpo is None:
        return "Listo, no lo anoté."
    lineas = ["Listo, quedó anotado ✅"]
    if cuerpo.get("duplicados"):
        lineas.append(f"{len(cuerpo['duplicados'])} ya estaban en tu cuaderno; no los dupliqué.")
    if cuerpo.get("saldo_caja_negocio") is not None:
        lineas.append(f"Caja del negocio hoy: {soles(Decimal(str(cuerpo['saldo_caja_negocio'])))}")
    if alertas := cuerpo.get("alertas_disparadas"):
        lineas.append(f"⚠ Ojo: {alertas[0].get('titulo') or alertas[0].get('insight')}.")
    return "\n".join(lineas)


def _confirmar(db, borrador: m.Borrador, confirmado: bool = True) -> dict:
    req = ConfirmarRequest(borrador_id=borrador.borrador_id, confirmado=confirmado,
                           correcciones=_correcciones(borrador) if confirmado else {})  # fmt: skip
    _status, cuerpo = servicio.confirmar(db, req)
    return _respuesta(_texto_confirmado(cuerpo))


def _boton(db, empresa: m.Empresa, valor: str) -> dict:
    accion, _, resto = (valor or "").partition(":")
    borrador_id, _, opcion = resto.partition(":")
    borrador = db.get(m.Borrador, borrador_id) if borrador_id else None
    if borrador is None or borrador.empresa_id != empresa.empresa_id:
        return _respuesta("Ese registro ya no existe. Vuelve a enviarlo, por favor.")
    if borrador.estado != EstadoBorrador.pendiente:
        return _respuesta("Ese registro ya estaba resuelto ✅")
    if accion == "confirmar":
        return _confirmar(db, borrador)
    if accion == "descartar":
        return _confirmar(db, borrador, confirmado=False)
    if accion == "corregir":
        _guardar_correcciones(db, borrador, {}, en_correccion=True)
        return _respuesta("¿Qué cambio? Escríbeme, por ejemplo: «fue por billetera», «fueron 15» o «era para la casa».")
    if accion == "opcion":
        campo, _, dato = opcion.partition("=")
        if campo == "salio_de_caja":
            if dato == "no":
                servicio.confirmar(db, ConfirmarRequest(borrador_id=borrador.borrador_id, confirmado=False))
                return _respuesta("Entendido: es plata de la casa, no la anoto en el negocio.")
            return _confirmar(db, borrador)
        _guardar_correcciones(db, borrador, {campo: dato})
        mov = _mov_actual(borrador)
        texto = f"Anotado: {resumen_movimiento(mov)} ✅ ¿Correcto?"
        if campo == "fecha_vencimiento" and (chequeo := servicio.chequeo_para(db, empresa.empresa_id, mov)):
            texto += "\n" + texto_chequeo(chequeo)
        return _respuesta(texto, _botones_confirmar(borrador.borrador_id))
    return _respuesta("No reconocí ese botón.")


def _en_correccion(db, empresa_id: str) -> m.Borrador | None:
    pendientes = db.scalars(select(m.Borrador).where(m.Borrador.empresa_id == empresa_id,
                                                     m.Borrador.estado == EstadoBorrador.pendiente)
                            .order_by(m.Borrador.creado_en.desc()).limit(5)).all()  # fmt: skip
    return next((b for b in pendientes if (b.correcciones or {}).get(EN_CORRECCION)), None)


def _aplicar_texto(db, borrador: m.Borrador, texto: str) -> dict | None:
    campo = (borrador.campos_faltantes or [None])[0] if not _correcciones(borrador) else None
    nuevas = parsear_correccion(texto, campo)
    if not nuevas:
        return None
    try:
        aplicar_correcciones(borrador.payload_propuesto, {**_correcciones(borrador), **nuevas})
    except ErrorAPI as exc:
        return _respuesta(exc.mensaje)
    _guardar_correcciones(db, borrador, nuevas)
    mov = aplicar_correcciones(borrador.payload_propuesto, _correcciones(borrador)).model_dump(mode="json")
    return _respuesta(f"Corregido: {resumen_movimiento(mov)} ✅ ¿Ahora sí?", _botones_confirmar(borrador.borrador_id))


def _asistente(db, empresa_id: str, texto: str) -> dict:
    r = orquestador.responder(db, empresa_id, texto, canal="whatsapp")
    partes = [r["respuesta"]]
    if ej := r.get("ejemplo_prestamo_informal"):
        partes.append(f"Ejemplo: recibes {soles(ej['recibes'])} → devuelves {soles(ej['devuelves'])} en "
                      f"{ej['dias']} días.")  # fmt: skip
    if r.get("respuesta_post"):
        partes.append(r["respuesta_post"])
    return _respuesta("\n".join(partes))


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


def _registro(db, empresa_id: str, canal: Canal, texto: str | None, media_url: str | None) -> dict:
    req = InterpretarRequest(empresa_id=empresa_id, canal=canal, texto=texto, media_url=media_url)
    try:
        res = servicio.interpretar(db, req)
    except NoInterpretable as exc:
        if any(d.get("campo") == "alcance" for d in exc.detalles):
            return _respuesta(exc.mensaje)
        if texto and canal == Canal.texto:
            return _asistente(db, empresa_id, texto)
        return _respuesta(exc.mensaje)
    respuesta = _texto_interpretacion(db, res)
    if res.get("transcripcion") and canal == Canal.voz:
        respuesta["respuesta_texto"] = f"🎙️ «{res['transcripcion']}»\n{respuesta['respuesta_texto']}"
    return respuesta


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
            respuesta = _registro(db, empresa.empresa_id, Canal.voz, body.texto, body.media_url)
        else:
            texto = (body.texto or "").strip()
            respuesta = None
            if pendiente := _en_correccion(db, empresa.empresa_id):
                respuesta = _aplicar_texto(db, pendiente, texto)
            if respuesta is None:
                if not texto:
                    respuesta = _respuesta("No recibí texto. Cuéntame qué vendiste o gastaste.")
                elif _PREGUNTA.search(texto) or _PREGUNTA.search(normalizar(texto)):
                    respuesta = _asistente(db, empresa.empresa_id, texto)
                else:
                    respuesta = _registro(db, empresa.empresa_id, Canal.texto, texto, None)
    except ErrorAPI as exc:
        respuesta = _respuesta(exc.mensaje)
    idempotencia.guardar_respuesta(db, body.mensaje_id, ENDPOINT, payload, 200, respuesta, empresa.empresa_id)
    return respuesta

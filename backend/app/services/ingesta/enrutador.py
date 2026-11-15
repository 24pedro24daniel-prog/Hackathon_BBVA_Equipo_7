"""Qué es cada mensaje del chat y a qué flujo va (chat de la app y WhatsApp usan esta misma lógica).

Con un borrador pendiente, el mensaje puede: confirmarlo ("sí", "dale"), corregirlo o responder su pregunta
("fue por billetera", "eran 3", "el 30 de noviembre"), cancelarlo ("no, bórralo") o no tener nada que ver (se trata
como mensaje nuevo). Sin borrador: un movimiento nuevo → registro; una pregunta, saludo o charla → asistente.

Primero deciden las reglas. Solo si dudan (y hay LLM) se hace UNA llamada corta al LLM para clasificar; si el LLM
no responde se usa lo que dijeron las reglas. Las cifras que proponga el LLM tienen que estar en el texto.
"""

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation

from app.core.config import settings
from app.core.errors import ErrorAPI, NoInterpretable
from app.core.meta import construir_meta
from app.core.reloj import hoy
from app.db import models as m
from app.schemas.common import Canal, EstadoBorrador, MetodoPago, OrigenMonto, TipoMovimiento
from app.schemas.ingesta import ConfirmarRequest, InterpretarRequest, MovimientoBorrador
from app.services.asistente import orquestador
from app.services.ingesta import catalogo as cat_mod
from app.services.ingesta import extractor, llm_client, servicio, traza_llm
from app.services.ingesta.servicio import aplicar_correcciones, resumen_movimiento
from app.services.ingesta.texto import (
    MESES,
    ResultadoFecha,
    fecha_corta,
    fecha_larga,
    normalizar,
    numeros,
    parsear_fecha,
    soles,
    valores_en_texto,
)

log = logging.getLogger("cajaclara.chat")

PROMPT_VERSION = "chat-router-v1"
EN_CORRECCION = "_en_correccion"
T = TipoMovimiento

PREGUNTA = re.compile(r"\?|^¿|\bcomo va\b|\bpor que\b|\bprestamo\b|^y si\b|\bcuanto tengo\b|\bme alcanza\b|\bque hago\b|"
                      r"\bque es\b|\bayuda\b|^hola\b|^buen[oa]s\b|\bcuanto (vendi|gane|saque|debo|me deben)\b|"
                      r"\bcomo (estoy|voy|me fue|me ha ido)\b|\breportes?\b|\bresumen\b")  # fmt: skip
# Respuesta a la pregunta "¿salió de la caja?" (chips "Sí, salió de la caja" / "No, no salió de la caja")
_SALIO_NO = re.compile(r"^no\b")
_SALIO_SI = re.compile(r"^(si|sip|sii+|ya|dale|claro|correcto|exacto|salio|yes|afirmativo)\b")
_CHARLA = re.compile(r"^(hola|holi|ola|alo|hey|buen[oa]s|que tal|como estas|gracias|muchas gracias|grax|mil gracias|"
                     r"chau|chao|adios|hasta luego|nos vemos|genial|chevere|excelente|jaja\w*|ok gracias|ya gracias)\b")  # fmt: skip
_CONFIRMAR = re.compile(r"^(si|sip|sii+|ya|dale|ok|okey|okay|listo|correcto|exacto|eso|asi es|esta bien|todo bien|"
                        r"perfecto|confirmo|confirmado|guardalo|guarda|anotalo|anota|registralo|de una|va|claro|bien|"
                        r"bacan|ya esta)( (si|ya|dale|esta bien|correcto|nomas|gracias|porfa|por favor|guardalo|"
                        r"anotalo|asi|asi esta bien|eso es|todo bien))*$")  # fmt: skip
_CANCELAR = re.compile(r"\b(borra\w*|cancela\w*|descarta\w*|olvida\w*|no lo (anotes|guardes|registres)|dejalo|"
                       r"ya no|no va)\b|^no( gracias| nada| mejor no)?$")  # fmt: skip
_MARCA_CORRECCION = re.compile(r"^(no|era|eran|fue|fueron|es|son|mejor|perdon|me equivoque|corrige|cambia|cambialo|"
                               r"en realidad|pero|sino)\b")  # fmt: skip
_VERBO_MOV = re.compile(r"\b(vendi\w*|pedi|compre|pague|gaste|saque|fie|cobre|me pago|me pagaron|me prestaron|"
                        r"me fiaron|me yapearon|retire|deposite|le pague)\b")  # fmt: skip
_MONEDA = re.compile(r"\b(soles|sol|lucas|luca)\b|s/")
_CANTIDAD = re.compile(r"\b(eran|fueron|son|vendi|cantidad|unidades)\b")
_CONTRAPARTE = re.compile(r"^(?:no,? )?(?:era|fue|es)?\s*(?:a|al|para|de)\s+(?:(?:la|el)\s+)?"
                          r"(?:(?:senora|senor|sra|sr|don|dona|vecina|vecino)\s+)?([a-z]+)$")  # fmt: skip


@dataclass
class Decision:
    accion: str  # confirmar | corregir | cancelar | asistente | nuevo
    correcciones: dict = field(default_factory=dict)
    fuente: str = "reglas"  # reglas | llm | reglas_fallback (el LLM no respondió)


@dataclass
class Resultado:
    tipo: str  # registro | borrador_actualizado | guardado | descartado | asistente
    mensaje: str | None = None
    interpretacion: dict | None = None
    confirmacion: dict | None = None
    asistente: dict | None = None
    borrador_id: str | None = None
    transcripcion: str | None = None
    conversacion_id: str | None = None
    meta: dict | None = None


# ── borrador: correcciones guardadas y estado actual ────────────────────────────────────────────


def correcciones_de(borrador: m.Borrador) -> dict:
    return {k: v for k, v in (borrador.correcciones or {}).items() if not k.startswith("_")}


def guardar_correcciones(db, borrador: m.Borrador, nuevas: dict, en_correccion: bool = False) -> None:
    borrador.correcciones = {**correcciones_de(borrador), **nuevas, EN_CORRECCION: en_correccion}
    db.commit()


def es_cuaderno(borrador: m.Borrador) -> bool:
    return borrador.canal == Canal.foto and "fiados" in (borrador.payload_propuesto or {})


def mov_actual(borrador: m.Borrador) -> dict:
    corr = {k: v for k, v in correcciones_de(borrador).items() if k != "salio_de_caja"}
    try:
        return aplicar_correcciones(borrador.payload_propuesto, corr, MovimientoBorrador).model_dump(mode="json")
    except ErrorAPI:
        return {**borrador.payload_propuesto, **corr}


def faltantes(borrador: m.Borrador, mov: dict) -> list[str]:
    """Campos que el borrador todavía necesita (los que el usuario ya respondió salen de la lista)."""
    corr = correcciones_de(borrador)
    pendientes = []
    for campo in borrador.campos_faltantes or []:
        if campo == "salio_de_caja" or (campo == "monto" and _valor(borrador.origen_monto) == "estimado"):
            if campo not in corr:
                pendientes.append(campo)
        elif not mov.get(campo):
            pendientes.append(campo)
    return pendientes


def _vacios(borrador: m.Borrador, mov: dict) -> list[str]:
    """Faltantes que de verdad impiden guardar (no basta con decir "sí")."""
    return [c for c in faltantes(borrador, mov) if c != "salio_de_caja" and not mov.get(c)]


def _valor(x):
    return getattr(x, "value", x)


def opciones_fecha(borrador: m.Borrador) -> list[date]:
    dia = borrador.creado_en.date() if borrador.creado_en else hoy()
    r = parsear_fecha(normalizar(borrador.texto_original or ""), dia)
    return [f for f in r.opciones if f >= hoy()] if r.ambigua else []


def _es_pedido_credito(mov: dict) -> bool:
    return mov.get("tipo") == T.compra.value and mov.get("metodo_pago") == MetodoPago.credito.value


def _pregunta(borrador: m.Borrador, campo: str, mov: dict) -> str:
    if campo == (borrador.campos_faltantes or [None])[0] and borrador.pregunta_aclaratoria:
        return borrador.pregunta_aclaratoria
    if campo == "fecha_vencimiento":
        ops = opciones_fecha(borrador)
        if len(ops) > 1:
            return "¿Lo pagas el " + " o el ".join(fecha_larga(f) for f in ops) + "?"
        return "¿Para qué día es el pago?"
    if campo == "contraparte":
        tipo = mov.get("tipo")
        return {"venta": "¿A quién le fiaste?", "cobro_fiado": "¿Quién te pagó?",
                "compra": "¿A qué proveedor le hiciste el pedido?",
                "pago_proveedor": "¿A qué proveedor le pagaste?"}.get(tipo, "¿Con quién fue?")  # fmt: skip
    if campo == "monto":
        return "¿De cuánto fue?"
    return "¿Me confirmas ese dato?"


def interpretacion_actual(db, borrador: m.Borrador, meta: dict | None = None) -> dict:
    """El borrador (con las correcciones de la conversación) con la MISMA forma que /ingesta/interpretar."""
    mov = mov_actual(borrador)
    falt = faltantes(borrador, mov)
    corr = correcciones_de(borrador)
    origen = OrigenMonto.dicho_por_usuario.value if "monto" in corr else _valor(borrador.origen_monto)
    confianza = 0.95 if not falt else float(borrador.confianza or Decimal("0.6"))
    res: dict = {
        "borrador_id": borrador.borrador_id,
        "transcripcion": None,
        "movimiento_propuesto": mov,
        "origen_monto": origen,
        "confianza": confianza,
        "campos_faltantes": falt,
        "pregunta_aclaratoria": _pregunta(borrador, falt[0], mov) if falt else None,
        "meta": meta or construir_meta("reglas-chat", extractor.VERSION_REGLAS).model_dump(mode="json"),
    }
    if falt and falt[0] == "fecha_vencimiento" and (ops := opciones_fecha(borrador)):
        res["opciones_aclaracion"] = [{"valor": f.isoformat(), "texto": fecha_corta(f)} for f in ops]
    elif falt and falt[0] == "salio_de_caja":
        res["opciones_aclaracion"] = [{"valor": "si", "texto": "Sí, salió de la caja"},
                                      {"valor": "no", "texto": "No, no salió de la caja"}]  # fmt: skip
    if chequeo := servicio.chequeo_para(db, borrador.empresa_id, mov, res.get("opciones_aclaracion")):
        res["chequeo_pedido"] = chequeo
    return res


# ── texto libre → correcciones ──────────────────────────────────────────────────────────────────


def _elegir_opcion(t: str, opciones: list[date]) -> date | None:
    """ "noviembre" / "este mes" / "el próximo" → una de las fechas que se ofrecieron."""
    for nombre, mes in MESES.items():
        if re.search(rf"\b{nombre}\b", t):
            return next((f for f in opciones if f.month == mes), None)
    if re.search(r"\b(este mes|el primero|la primera|el de este mes)\b", t):
        return opciones[0]
    if re.search(r"\b(proximo|siguiente|el otro|que viene|el segundo|la segunda)\b", t) and len(opciones) > 1:
        return opciones[1]
    return None


def _dia_como_fecha(dia: int, opciones: list[date]) -> date | None:
    coinciden = [f for f in opciones if f.day == dia]
    if coinciden:  # repite el día que se le ofreció: la más cercana (igual que el primer botón)
        return coinciden[0]
    r = parsear_fecha(f"para el {dia}", hoy())
    return r.fecha


def parsear_correccion(texto: str, mov: dict | None = None, campo: str | None = None,
                       opciones: list[date] | None = None, cat: cat_mod.Catalogo | None = None) -> dict:  # fmt: skip
    """Texto libre → correcciones ("fue por billetera", "eran 3", "no, 15 soles", "el 30 de noviembre", "a Rosa").

    `mov` es el borrador actual y `campo` lo que se le preguntó (si se le preguntó algo).
    """
    t = normalizar(texto)
    mov = mov or {}
    c: dict = {}
    if re.search(r"\b(billetera|yape|yapeo|yapearon|plin|digital)\b", t):
        c["metodo_pago"] = "billetera_digital"
    elif re.search(r"\b(efectivo|cash|en mano)\b", t):
        c["metodo_pago"] = "efectivo"
    elif re.search(r"\b(tarjeta|pos)\b", t):
        c["metodo_pago"] = "tarjeta"
    elif re.search(r"\btransferencia\b", t):
        c["metodo_pago"] = "transferencia"
    elif re.search(r"\b(fiado|credito)\b", t):
        c["metodo_pago"] = "credito"
    if re.search(r"\bpara la casa\b|\bpersonal\b|\bpara mi\b|\bretiro\b|\blo saque\b|\bde la caja\b", t):
        c["tipo"] = "retiro_personal"
    elif re.search(r"\bventa\b|\bvendi\b", t) and mov.get("tipo") not in (None, "venta"):
        c["tipo"] = "venta"

    # Fecha de pago (pedido a crédito, préstamo, fiado)
    pide_fecha = campo == "fecha_vencimiento" or mov.get("tipo") == T.prestamo_recibido.value or (
        mov.get("metodo_pago") == MetodoPago.credito.value and mov.get("tipo") in (T.compra.value, T.venta.value))
    fecha = parsear_fecha(t, hoy()) if pide_fecha else ResultadoFecha()
    if fecha.fecha:
        c["fecha_vencimiento"] = fecha.fecha.isoformat()
    elif pide_fecha and opciones and (elegida := _elegir_opcion(t, opciones)):
        c["fecha_vencimiento"] = elegida.isoformat()

    cifras = [n for n in numeros(t) if n.texto not in ("un", "una", "uno", "medio", "media")
              and not (fecha.inicio is not None and fecha.inicio <= n.inicio < (fecha.fin or 0))]  # fmt: skip
    if cifras and campo == "fecha_vencimiento" and "fecha_vencimiento" not in c:
        n = cifras[0]
        if n.valor == n.valor.to_integral_value() and 1 <= n.valor <= 31 and not _MONEDA.search(t):
            if f := _dia_como_fecha(int(n.valor), opciones or []):
                c["fecha_vencimiento"] = f.isoformat()
            cifras = cifras[1:]
    if cifras and campo != "contraparte":
        n = cifras[0]
        items = mov.get("items") or []
        es_cantidad = (len(items) == 1 and campo != "monto" and n.valor == n.valor.to_integral_value()
                       and n.valor <= 50 and not _MONEDA.search(t) and _CANTIDAD.search(t))  # fmt: skip
        if es_cantidad:
            item = items[0]
            precio = Decimal(str(item["precio_unitario"]))
            total = (n.valor * precio).quantize(Decimal("0.01"))
            c["items"] = [{**item, "cantidad": str(n.valor), "subtotal": str(total)}]
            c["monto"] = str(total)
        else:
            c["monto"] = str(n.valor)

    con_contraparte = mov.get("tipo") in ("venta", "cobro_fiado", "compra", "pago_proveedor", "prestamo_recibido",
                                          "pago_prestamo")  # fmt: skip
    if con_contraparte and not c:
        nombre = None
        if campo == "contraparte":
            nombre = re.sub(r"^(a|al|a la|el|la|fue|era|de)\s+", "", t).strip()
        elif mm := _CONTRAPARTE.match(t):
            nombre = mm.group(1)
        if nombre:
            encontrado = None
            if cat is not None:
                encontrado = cat.buscar_cliente(nombre) if mov.get("tipo") in ("venta", "cobro_fiado") \
                    else cat.buscar_proveedor(nombre)  # fmt: skip
            c["contraparte"] = encontrado.nombre if encontrado else nombre.title()[:100]
    return c


# ── clasificación con LLM (solo si las reglas dudan) ────────────────────────────────────────────

_TOOL = {
    "type": "function",
    "function": {
        "name": "clasificar_mensaje",
        "description": "Qué quiere decir el dueño de la bodega con su mensaje, dado el registro que está pendiente.",
        "parameters": {
            "type": "object",
            "properties": {
                "accion": {"type": "string",
                           "enum": ["confirmar", "corregir", "cancelar", "nuevo_movimiento", "pregunta_o_charla"]},
                "monto": {"type": ["number", "null"], "description": "Nuevo monto, solo si lo dijo"},
                "cantidad": {"type": ["number", "null"], "description": "Nueva cantidad del producto, solo si la dijo"},
                "metodo_pago": {"type": ["string", "null"], "enum": [x.value for x in MetodoPago] + [None]},
                "tipo": {"type": ["string", "null"], "enum": [x.value for x in TipoMovimiento] + [None]},
                "contraparte": {"type": ["string", "null"]},
                "fecha_vencimiento": {"type": ["string", "null"], "description": "YYYY-MM-DD"},
            },
            "required": ["accion"],
        },
    },
}

_SISTEMA = """Eres el clasificador del chat de TuCaserito (app para el dueño de una bodega en Perú). Hoy es {hoy}.
Hay un registro pendiente que el dueño aún no confirma: {resumen}.{pregunta}
Decide qué hace su nuevo mensaje y llama a clasificar_mensaje:
- confirmar: acepta el registro tal cual ("sí", "dale", "ya, guárdalo").
- corregir: cambia o completa un dato del registro, o responde la pregunta pendiente. Llena SOLO los campos que \
cambian, con cifras que él dijo (no calcules).
- cancelar: no quiere anotarlo.
- nuevo_movimiento: cuenta OTRA venta, compra o pago distinto al pendiente.
- pregunta_o_charla: pregunta sobre su negocio, saluda, agradece o cualquier otra cosa."""

_ACCIONES = {"confirmar": "confirmar", "corregir": "corregir", "cancelar": "cancelar", "nuevo_movimiento": "nuevo",
             "pregunta_o_charla": "asistente"}  # fmt: skip


def _decimal(v) -> Decimal | None:
    try:
        return Decimal(str(v)) if v is not None else None
    except InvalidOperation:
        return None


def _correcciones_llm(datos: dict, texto: str, mov: dict) -> dict:
    dichos = valores_en_texto(texto)
    c: dict = {}
    if (monto := _decimal(datos.get("monto"))) and monto > 0 and monto.quantize(Decimal("0.01")) in dichos:
        c["monto"] = str(monto)
    cantidad = _decimal(datos.get("cantidad"))
    items = mov.get("items") or []
    if cantidad and cantidad > 0 and cantidad.quantize(Decimal("0.01")) in dichos and len(items) == 1 and "monto" not in c:
        precio = Decimal(str(items[0]["precio_unitario"]))
        total = (cantidad * precio).quantize(Decimal("0.01"))
        c["items"] = [{**items[0], "cantidad": str(cantidad), "subtotal": str(total)}]
        c["monto"] = str(total)
    if datos.get("metodo_pago") in {x.value for x in MetodoPago}:
        c["metodo_pago"] = datos["metodo_pago"]
    if datos.get("tipo") in {x.value for x in TipoMovimiento} and datos["tipo"] != mov.get("tipo"):
        c["tipo"] = datos["tipo"]
    if isinstance(datos.get("contraparte"), str) and datos["contraparte"].strip():
        c["contraparte"] = datos["contraparte"].strip()[:100]
    try:
        f = date.fromisoformat(str(datos.get("fecha_vencimiento")))
        if f >= hoy():
            c["fecha_vencimiento"] = f.isoformat()
    except ValueError:
        pass
    return c


def _clasificar_llm(db, borrador: m.Borrador, texto: str, mov: dict, falt: list[str]) -> Decision | None:
    if not settings.llm_configurado:
        return None
    pregunta = f" Le preguntaste: «{_pregunta(borrador, falt[0], mov)}»" if falt else ""
    sistema = _SISTEMA.format(hoy=hoy().isoformat(), resumen=resumen_movimiento(mov) if mov.get("tipo") else
                              "fiados leídos de una foto del cuaderno", pregunta=pregunta)  # fmt: skip
    traza = traza_llm.crear(db, borrador.empresa_id, "extractor", PROMPT_VERSION, "borrador")
    try:
        msg = llm_client.chat_completion(
            [{"role": "system", "content": sistema}, {"role": "user", "content": texto}],
            tools=[_TOOL], tool_choice={"type": "function", "function": {"name": "clasificar_mensaje"}},
            temperature=0, max_tokens=150, timeout_s=min(settings.LLM_TIMEOUT_S, 8), traza=traza,
        )  # fmt: skip
        llamada = (msg.get("tool_calls") or [{}])[0].get("function", {}).get("arguments")
        datos = json.loads(llamada) if isinstance(llamada, str) else llamada
        accion = _ACCIONES[datos["accion"]]
    except llm_client.LLMNoDisponible as exc:
        log.warning("Clasificador del chat: uso reglas (%s)", exc)
        return Decision("nuevo", fuente="reglas_fallback")
    except (KeyError, TypeError, ValueError, AttributeError, IndexError):
        if traza:
            traza.marcar("rechazada_validacion")
        return Decision("nuevo", fuente="reglas_fallback")
    if traza:
        traza.marcar("aceptada", referencia_tipo="borrador", referencia_id=borrador.borrador_id)
    corr = _correcciones_llm(datos, texto, mov) if accion == "corregir" else {}
    return Decision(accion, corr, fuente="llm")


def decidir(db, borrador: m.Borrador, texto: str, cat: cat_mod.Catalogo | None = None) -> Decision:
    """¿Qué hace este mensaje con el borrador pendiente?"""
    t = normalizar(texto)
    if es_cuaderno(borrador):
        if _CANCELAR.search(t):
            return Decision("cancelar")
        if _CONFIRMAR.match(t):
            return Decision("confirmar")
        return Decision("asistente" if PREGUNTA.search(texto) or PREGUNTA.search(t) or _CHARLA.match(t) else "nuevo")

    mov = mov_actual(borrador)
    falt = faltantes(borrador, mov)
    campo = falt[0] if falt else None
    if campo == "salio_de_caja":  # se resuelve primero: "de la caja" no es una corrección de tipo en esta respuesta
        if _SALIO_NO.match(t):
            return Decision("cancelar")
        if _SALIO_SI.match(t):
            return Decision("confirmar")
    nuevas = parsear_correccion(texto, mov, campo, opciones_fecha(borrador), cat)

    if _CANCELAR.search(t) and not nuevas:
        return Decision("cancelar")
    if _CONFIRMAR.match(t):
        return Decision("confirmar")
    es_pregunta = bool(PREGUNTA.search(texto) or PREGUNTA.search(t))
    mov_nuevo = bool(_VERBO_MOV.search(t))
    if nuevas and not es_pregunta and (not mov_nuevo or _MARCA_CORRECCION.match(t)):
        return Decision("corregir", nuevas)
    if es_pregunta and not nuevas:
        return Decision("asistente")
    if _CHARLA.match(t) and not nuevas and not mov_nuevo:
        return Decision("asistente")

    # Las reglas dudan ("vendí 3, no 2", "eso no, la otra", "fue la vecina"): una sola llamada al LLM.
    if (llm := _clasificar_llm(db, borrador, texto, mov, falt)) is not None:
        if llm.accion == "corregir":
            llm.correcciones = {**llm.correcciones, **nuevas}
        if llm.fuente == "llm":
            return llm
    fallback = "reglas_fallback" if llm is not None else "reglas"
    if nuevas and not mov_nuevo:
        return Decision("corregir", nuevas, fuente=fallback)
    return Decision("nuevo", fuente=fallback)


# ── acciones ────────────────────────────────────────────────────────────────────────────────────


def texto_guardado(cuerpo: dict) -> str:
    lineas = ["Listo, quedó anotado ✅"]
    if cuerpo.get("duplicados"):
        lineas.append(f"{len(cuerpo['duplicados'])} ya estaban en tu cuaderno; no los dupliqué.")
    if cuerpo.get("saldo_caja_negocio") is not None:
        lineas.append(f"Caja del negocio hoy: {soles(Decimal(str(cuerpo['saldo_caja_negocio'])))}")
    if alertas := cuerpo.get("alertas_disparadas"):
        lineas.append(f"⚠ Ojo: {alertas[0].get('titulo') or alertas[0].get('insight')}.")
    return "\n".join(lineas)


def _meta_decision(decision: Decision | None) -> dict:
    if decision is not None and decision.fuente == "llm":
        return construir_meta("llm-chat", settings.LLM_MODEL, prompt_version=PROMPT_VERSION).model_dump(mode="json")
    return construir_meta("reglas-chat", extractor.VERSION_REGLAS,
                          fallback_usado=decision is not None and decision.fuente == "reglas_fallback"
                          ).model_dump(mode="json")  # fmt: skip


def confirmar(db, borrador: m.Borrador, decision: Decision | None = None) -> Resultado:
    meta = _meta_decision(decision)
    if not es_cuaderno(borrador):
        mov = mov_actual(borrador)
        if vacios := _vacios(borrador, mov):
            return Resultado("borrador_actualizado", mensaje=f"Antes de guardarlo: {_pregunta(borrador, vacios[0], mov)}",
                             interpretacion=interpretacion_actual(db, borrador, meta),
                             borrador_id=borrador.borrador_id, meta=meta)  # fmt: skip
    _status, cuerpo = servicio.confirmar(db, ConfirmarRequest(borrador_id=borrador.borrador_id, confirmado=True))
    return Resultado("guardado", mensaje=texto_guardado(cuerpo), confirmacion=cuerpo, borrador_id=borrador.borrador_id,
                     meta=meta)  # fmt: skip


def descartar(db, borrador: m.Borrador, decision: Decision | None = None) -> Resultado:
    era_personal = "salio_de_caja" in (borrador.campos_faltantes or [])
    servicio.confirmar(db, ConfirmarRequest(borrador_id=borrador.borrador_id, confirmado=False))
    mensaje = ("Ya, entonces no lo anoto: aquí solo va la plata del negocio." if era_personal
               else "Ya, no lo anoto. Si quieres, me lo cuentas de nuevo.")  # fmt: skip
    return Resultado("descartado", mensaje=mensaje, borrador_id=borrador.borrador_id, meta=_meta_decision(decision))


def corregir(db, borrador: m.Borrador, nuevas: dict, decision: Decision | None = None,
             autoguardar: bool = True) -> Resultado:  # fmt: skip
    """Aplica la corrección. Si respondía la pregunta pendiente y ya no falta nada, lo guarda de una vez
    (salvo un pedido a crédito: ese se muestra con el chequeo de caja antes de guardar)."""
    meta = _meta_decision(decision)
    if not nuevas:
        return Resultado("borrador_actualizado", mensaje="¿Qué le cambio? Dime el monto, cómo te pagaron o lo que haya "
                         "que arreglar.", interpretacion=interpretacion_actual(db, borrador, meta),
                         borrador_id=borrador.borrador_id, meta=meta)  # fmt: skip
    respondia = bool(faltantes(borrador, mov_actual(borrador)))
    try:
        aplicar_correcciones(borrador.payload_propuesto, {**correcciones_de(borrador), **nuevas}, MovimientoBorrador)
    except ErrorAPI as exc:
        return Resultado("borrador_actualizado", mensaje=f"Mmm, ese dato no me cuadra. {exc.mensaje}",
                         interpretacion=interpretacion_actual(db, borrador, meta), borrador_id=borrador.borrador_id,
                         meta=meta)  # fmt: skip
    guardar_correcciones(db, borrador, nuevas)
    mov = mov_actual(borrador)
    falt = faltantes(borrador, mov)
    if autoguardar and respondia and not falt and not _es_pedido_credito(mov):
        return confirmar(db, borrador, decision)
    interp = interpretacion_actual(db, borrador, meta)
    if falt:
        mensaje = interp["pregunta_aclaratoria"]
    elif interp.get("chequeo_pedido"):
        mensaje = f"Listo: {resumen_movimiento(mov)}. Mira cómo quedaría tu caja ese día y me dices si lo guardo."
    else:
        mensaje = f"Listo, lo cambié: {resumen_movimiento(mov)}. ¿Ahora sí lo guardo?"
    return Resultado("borrador_actualizado", mensaje=mensaje, interpretacion=interp, borrador_id=borrador.borrador_id,
                     meta=meta)  # fmt: skip


def asistente(db, empresa_id: str, texto: str, conversacion_id: str | None = None, canal: str = "app") -> Resultado:
    r = orquestador.responder(db, empresa_id, texto, conversacion_id, canal)
    partes = [r["respuesta"]]
    if ej := r.get("ejemplo_prestamo_informal"):
        partes.append(f"Ejemplo: recibes {soles(ej['recibes'])} → devuelves {soles(ej['devuelves'])} en "
                      f"{ej['dias']} días.")  # fmt: skip
    if r.get("respuesta_post"):
        partes.append(r["respuesta_post"])
    meta = r.get("meta")
    meta = meta.model_dump(mode="json") if hasattr(meta, "model_dump") else meta
    return Resultado("asistente", mensaje="\n".join(partes), asistente=r, conversacion_id=r.get("conversacion_id"),
                     meta=meta)  # fmt: skip


def registro(db, empresa_id: str, texto: str | None, *, canal: Canal = Canal.texto, media_url: str | None = None,
             transcrito: tuple | None = None, conversacion_id: str | None = None,
             canal_asistente: str = "app") -> Resultado:  # fmt: skip
    """Mensaje nuevo → borrador. Si no es un movimiento, lo responde el asistente."""
    req = InterpretarRequest(empresa_id=empresa_id, canal=canal, texto=texto, media_url=media_url)
    try:
        res = servicio.interpretar(db, req, transcrito)
    except NoInterpretable as exc:
        escuchado = transcrito[0] if transcrito else texto
        if any(d.get("campo") == "alcance" for d in exc.detalles):
            return Resultado("asistente", mensaje=exc.mensaje, conversacion_id=conversacion_id,
                             meta=construir_meta("reglas-chat", extractor.VERSION_REGLAS).model_dump(mode="json"))  # fmt: skip
        if escuchado and escuchado.strip():
            r = asistente(db, empresa_id, escuchado, conversacion_id, canal_asistente)
            r.transcripcion = transcrito[1] if transcrito else None
            return r
        raise
    if res.get("pregunta_aclaratoria"):
        mensaje = res["pregunta_aclaratoria"]
    elif res.get("chequeo_pedido"):
        mensaje = "Así lo entendí. Mira cómo quedaría tu caja ese día y me dices si lo guardo."
    else:
        mensaje = "Así lo entendí. ¿Lo guardo?"
    return Resultado("registro", mensaje=mensaje, interpretacion=res, borrador_id=res["borrador_id"],
                     transcripcion=res.get("transcripcion"), conversacion_id=conversacion_id, meta=res["meta"])  # fmt: skip


def es_charla(texto: str) -> bool:
    t = normalizar(texto)
    return bool(PREGUNTA.search(texto) or PREGUNTA.search(t) or _CHARLA.match(t))


def procesar_texto(db, empresa_id: str, texto: str, borrador: m.Borrador | None = None, *,
                   conversacion_id: str | None = None, canal_asistente: str = "app", autoguardar: bool = True,
                   canal: Canal = Canal.texto, media_url: str | None = None,
                   transcrito: tuple | None = None) -> Resultado:  # fmt: skip
    """Punto de entrada común (chat de la app y WhatsApp)."""
    texto = (texto or "").strip()
    if borrador is not None and (borrador.empresa_id != empresa_id or borrador.estado != EstadoBorrador.pendiente):
        borrador = None
    if borrador is not None and texto:
        cat = None if es_cuaderno(borrador) else cat_mod.cargar(db, empresa_id)
        d = decidir(db, borrador, texto, cat)
        r = None
        if d.accion == "confirmar":
            r = confirmar(db, borrador, d)
        elif d.accion == "cancelar":
            r = descartar(db, borrador, d)
        elif d.accion == "corregir":
            r = corregir(db, borrador, d.correcciones, d, autoguardar)
        elif d.accion == "asistente":
            r = asistente(db, empresa_id, texto, conversacion_id, canal_asistente)
        if r is not None:
            if transcrito:
                r.transcripcion = transcrito[1]
            return r
    elif texto and es_charla(texto):
        r = asistente(db, empresa_id, texto, conversacion_id, canal_asistente)
        if transcrito:
            r.transcripcion = transcrito[1]
        return r
    return registro(db, empresa_id, texto or None, canal=canal, media_url=media_url, transcrito=transcrito,
                    conversacion_id=conversacion_id, canal_asistente=canal_asistente)  # fmt: skip

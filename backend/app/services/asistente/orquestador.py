"""Intención → herramientas → respuesta (A8, A10). Guarda los mensajes en `conversaciones`.

Intenciones: estado_caja, explicar_alerta, simular, prestamo, fuera_de_alcance (+ concepto, crear_meta, otro).
- La intención se clasifica por reglas y cada intención tiene un plan fijo de herramientas (funciones de B).
- La plantilla arma la respuesta con esas cifras. Si hay LLM, este solo la REDACTA mejor; el verificador revisa
  que toda cifra del texto exista en los resultados. Si no pasa → se responde la plantilla
  (`verificacion_cifras.ok = false`, `fallback_usado = true`). El LLM nunca calcula cifras.
- prestamo, fuera_de_alcance y concepto usan textos fijos revisados (no pasan por el LLM).
- otro (saludo, gracias, charla o mensaje poco claro): si hay LLM, responde con naturalidad dentro del alcance y SIN
  cifras (el verificador solo admite las del propio mensaje); si no, una plantilla corta según el tipo de mensaje.
- Ningún texto del LLM se acepta si trae porcentajes, habla de "la casa" o de datos simulados (reglas de producto).
"""

import json
import logging
import re
from dataclasses import dataclass, field

from sqlalchemy import Integer, cast, func, select

from app.core.config import settings
from app.core.ids import nuevo_id
from app.core.meta import construir_meta
from app.core.reloj import ahora
from app.db import models as m
from app.schemas.common import CanalNotificacion, IntencionAsistente, RolMensaje
from app.services.asistente import herramientas, plantillas, verificador
from app.services.ingesta import llm_client, traza_llm
from app.services.ingesta.texto import normalizar, numeros

log = logging.getLogger("cajaclara.asistente")

PROMPT_VERSION = "asistente-v3"
VERSION_PLANTILLAS = "plantillas-1.0.0"
I = IntencionAsistente

_FUERA = re.compile(
    r"\b(cripto\w*|bitcoin|invertir|inversion(es)?|acciones de|bolsa de valores|forex|plazo fijo|abogado|demanda|"
    r"juicio|denuncia|igv|declaracion de renta|que regimen|multa|mibanco|bcp|interbank|bbva|scotiabank|"
    r"caja (huancayo|arequipa|piura|trujillo|cusco))\b|"
    r"\b(que|cual|en que|donde)\s+(banco|caja|financiera|entidad|cooperativa)\b|"
    r"\b(recomiendas?|recomiendame|me conviene)\b.*\b(banco|caja|financiera|credito|prestamo|entidad)\b"
)
_PRESTAMO = re.compile(r"\b(prestamo|prestamos|prestar|prestamista|gota a gota|endeudarme|me presten)\b")
_SIMULAR = re.compile(r"^y si\b|\bsi (pido|pago|cobro|saco|reduzco|pidiera|pagara|pagase)\b|\b(simula|simular)\b|"
                      r"\ben (\d+|dos|tres|cuatro) partes\b|\b(pedir|pido) menos\b")  # fmt: skip
_EXPLICAR = re.compile(r"\bpor que\b|\bme va a faltar\b|\bfalt(a|ar|aria|aran)\b|\balertas?\b|\bme alcanza\b|"
                       r"\bno me alcanza\b")  # fmt: skip
_ESTADO = re.compile(r"\bcomo va\b|\bmi caja\b|\bcuanto tengo\b|\bcomo estoy\b|\bsaldo\b|\bcuanto hay\b|\bresumen\b|"
                     r"\bcomo me va\b|\bcuanta plata\b")  # fmt: skip
_CONCEPTO = re.compile(r"\bque es\b|\bque significa\b|\bexplicame\b|\bpara que sirve\b")
_META = re.compile(r"\b(meta|metas|ahorrar|apartar|sueldo fijo|ponerme un sueldo)\b")
_SALUDO = re.compile(r"^(hola|holi|buenas|buenos dias|buenas tardes|buenas noches|que tal|hey|ola|alo)\b")
_GRACIAS = re.compile(r"\b(gracias|grax|muchas gracias|te pasaste|genial|chevere|excelente|perfecto)\b")
_DESPEDIDA = re.compile(r"\b(chau|chao|adios|hasta luego|hasta manana|nos vemos|bye)\b")
_PROHIBIDO_LLM = re.compile(r"%|\bpor ciento\b|\bcasa\b|\bprobabilidad|\bsimula|\bsint[eé]tic|\bficticio|\bdemo\b")


def clasificar(mensaje: str) -> IntencionAsistente:
    t = normalizar(mensaje)
    if _FUERA.search(t):
        return I.fuera_de_alcance
    if _PRESTAMO.search(t):
        return I.prestamo
    if _SIMULAR.search(t):
        return I.simular
    if _EXPLICAR.search(t):
        return I.explicar_alerta
    if _ESTADO.search(t):
        return I.estado_caja
    if _CONCEPTO.search(t):
        return I.concepto
    if _META.search(t):
        return I.crear_meta
    return I.otro


@dataclass
class _Contexto:
    db: object
    empresa_id: str
    llamadas: list[dict] = field(default_factory=list)

    def usar(self, nombre: str, args: dict | None = None) -> dict:
        args = args or {}
        resultado = herramientas.ejecutar(self.db, self.empresa_id, nombre, args)
        self.llamadas.append({"nombre": nombre, "args": args, "resultado": resultado})
        return resultado

    @property
    def resultados(self) -> list:
        return [ll["resultado"] for ll in self.llamadas] + [ll["args"] for ll in self.llamadas]


def _pedido_principal(ctx: _Contexto) -> dict | None:
    items = ctx.usar("obtener_pedidos", {"estado": "pendiente"}).get("items") or []
    return max(items, key=lambda p: p["monto_pendiente"]) if items else None


def _monto_reducido(ctx: _Contexto, pedido: dict) -> float | None:
    chequeo = ctx.usar("chequear_pedido", {"proveedor": pedido["proveedor"], "monto": pedido["monto_pendiente"],
                                           "fecha_vencimiento": pedido["fecha_vencimiento"]})  # fmt: skip
    sugerida = next((s for s in chequeo.get("sugerencias", []) if s["accion"] == "reducir_pedido"), None)
    return sugerida.get("monto_sugerido") if sugerida else None


def _plan_estado(ctx: _Contexto, _mensaje: str) -> plantillas.Borrador:
    from app.core.reloj import hoy

    resumen = ctx.usar("obtener_resumen", {"periodo": hoy().strftime("%Y-%m")})
    forecast = ctx.usar("obtener_forecast", {"horizonte_dias": 30})
    return plantillas.estado_caja(resumen, forecast)


def _plan_explicar(ctx: _Contexto, _mensaje: str) -> plantillas.Borrador:
    alertas = ctx.usar("obtener_alertas", {"estado": "activa"}).get("items") or []
    alerta = min(alertas, key=lambda a: a["prioridad"]) if alertas else None
    simulacion = nuevo = None
    if alerta:
        pedido = _pedido_principal(ctx)
        if pedido:
            nuevo = _monto_reducido(ctx, pedido)
            if nuevo:
                simulacion = ctx.usar("simular", {"acciones": [
                    {"tipo": "reducir_pedido", "pedido_id": pedido["pedido_id"], "nuevo_monto": nuevo},
                    {"tipo": "pagar_en_partes", "pedido_id": pedido["pedido_id"], "partes": 2}]})  # fmt: skip
    return plantillas.explicar_alerta(alerta, simulacion, nuevo)


_PARTES = {"dos": 2, "tres": 3, "cuatro": 4}


def _acciones_de(ctx: _Contexto, mensaje: str) -> tuple[list[dict], list[str], bool]:
    t = normalizar(mensaje)
    acciones, descripcion, partes = [], [], False
    pedido = None
    if re.search(r"\bpartes\b|\b(pido|pedir|pidiera|pedido|reduzco|bajo)\b", t):
        pedido = _pedido_principal(ctx)
    if pedido and (m_partes := re.search(r"\ben (\d+|dos|tres|cuatro) partes\b", t)):
        n = int(m_partes.group(1)) if m_partes.group(1).isdigit() else _PARTES[m_partes.group(1)]
        acciones.append({"tipo": "pagar_en_partes", "pedido_id": pedido["pedido_id"], "partes": max(2, min(n, 12))})
        descripcion.append(f"pagas en {n} partes")
        partes = True
    if pedido and (m_pido := re.search(r"\b(?:pido|pedir|pidiera|pedido de|reduzco a|bajo a)\s+(?:s/\s*)?", t)):
        cifras = [n for n in numeros(t[m_pido.end():]) if n.valor > 10]
        nuevo = float(cifras[0].valor) if cifras else None
        if nuevo is None and re.search(r"\bmenos\b", t):
            nuevo = _monto_reducido(ctx, pedido)
        if nuevo:
            acciones.append({"tipo": "reducir_pedido", "pedido_id": pedido["pedido_id"], "nuevo_monto": nuevo})
            descripcion.append(f"pides S/ {nuevo:,.0f}".replace(",", " "))
    if re.search(r"\bcobr\w*\b.*\bfiados?\b|\bfiados?\b.*\bcobr\w*\b", t):
        fiados = ctx.usar("obtener_fiados", {"estado": "pendiente"}).get("items") or []
        if fiados:
            acciones.append({"tipo": "cobrar_fiados", "fiado_ids": [f["fiado_id"] for f in fiados]})
            descripcion.append("cobras tus fiados")
    return acciones, descripcion, partes


def _plan_simular(ctx: _Contexto, mensaje: str) -> plantillas.Borrador:
    acciones, descripcion, partes = _acciones_de(ctx, mensaje)
    if not acciones:
        return plantillas.Borrador(plantillas.SIMULAR_AYUDA)
    simulacion = ctx.usar("simular", {"acciones": acciones})
    return plantillas.simular(simulacion, " y ".join(descripcion), partes)


def _plan_prestamo(ctx: _Contexto, _mensaje: str) -> plantillas.Borrador:
    ejemplo = ctx.usar("explicar_concepto", {"tema": "prestamo_informal"})["ejemplo"]
    simulacion = None
    pedido = _pedido_principal(ctx)
    if pedido:
        acciones = [{"tipo": "pagar_en_partes", "pedido_id": pedido["pedido_id"], "partes": 2}]
        if nuevo := _monto_reducido(ctx, pedido):
            acciones.insert(0, {"tipo": "reducir_pedido", "pedido_id": pedido["pedido_id"], "nuevo_monto": nuevo})
        fiados = ctx.usar("obtener_fiados", {"estado": "pendiente"}).get("items") or []
        if fiados:
            acciones.append({"tipo": "cobrar_fiados", "fiado_ids": [f["fiado_id"] for f in fiados]})
        simulacion = ctx.usar("simular", {"acciones": acciones})
    return plantillas.prestamo(ejemplo, simulacion)


def _plan_concepto(ctx: _Contexto, mensaje: str) -> plantillas.Borrador:
    t = normalizar(mensaje)
    tema = next((v for k, v in plantillas.TEMAS_CONCEPTO.items() if k in t), None)
    if tema is None:
        return _plan_otro(ctx, mensaje)
    return plantillas.Borrador(ctx.usar("explicar_concepto", {"tema": tema})["texto"])


def _plan_otro(_ctx: _Contexto, mensaje: str) -> plantillas.Borrador:
    """Plantilla corta y natural según el tipo de mensaje (la usa también el LLM como respaldo)."""
    t = normalizar(mensaje)
    if _DESPEDIDA.search(t):
        texto = plantillas.DESPEDIDA
    elif _GRACIAS.search(t):
        texto = plantillas.GRACIAS
    elif _SALUDO.search(t):
        texto = plantillas.SALUDO
    else:
        texto = plantillas.AYUDA
    return plantillas.Borrador(texto, conversacional=True)


PLANES = {
    I.estado_caja: _plan_estado,
    I.explicar_alerta: _plan_explicar,
    I.simular: _plan_simular,
    I.prestamo: _plan_prestamo,
    I.concepto: _plan_concepto,
    I.fuera_de_alcance: lambda ctx, msg: plantillas.Borrador(plantillas.FUERA_DE_ALCANCE, ofrecer_humano=True),
    I.crear_meta: lambda ctx, msg: plantillas.Borrador(plantillas.CREAR_META),
    I.otro: _plan_otro,
}
CON_LLM = {I.estado_caja, I.explicar_alerta, I.simular}

_TONO = """Hablas como un vecino de confianza: español peruano sencillo, de tú, cálido y breve, nada robótico. \
Nunca uses porcentajes ni probabilidades (dilo con palabras o en soles). Nunca digas que los datos son \
simulados, ficticios, sintéticos o de demo, ni hables de «simulación» o «simulador» (di «si haces esto, te quedaría…»). Nunca hables de «la casa» ni de «plata de \
la casa»: lo que el dueño saca para él es «lo que sacaste de la caja», «tus retiros» o «tu sueldo». No recomiendes \
créditos, entidades ni inversiones."""

_SISTEMA = f"""Eres el asistente de TuCaserito para el dueño de una bodega en Perú. Te paso su pregunta y un BORRADOR \
de respuesta hecho con sus datos reales. Reescríbelo claro y breve (máximo 3 oraciones, sin listas). Usa SOLO las \
cifras que aparecen en el BORRADOR y escríbelas igual (por ejemplo «S/ 2 340»). No agregues cifras, fechas ni \
cálculos nuevos. {_TONO} Responde solo con el texto."""

_SISTEMA_CHARLA = f"""Eres el asistente de TuCaserito y conversas por chat con el dueño de una bodega en Perú \
({{negocio}}). {_TONO}
Tu tema es solo su negocio: su caja, ventas, gastos, fiados, pedidos a proveedores, pagos que se vienen, metas y \
cómo anotar sus movimientos (por voz, texto o foto). Si te saluda, agradece o se despide, respóndele con naturalidad \
y en una o dos oraciones, sin darle un menú de opciones. Si no queda claro qué quiere, hazle una pregunta corta y \
amable para entenderlo. Si pregunta algo que no es de su negocio, díselo con cariño y vuelve a su negocio.
No tienes sus números a la mano: NO digas cifras, montos ni fechas; si quiere saber de su plata, ofrécele revisar \
cómo va su caja. Responde solo con el texto (máximo 2 oraciones)."""


def redactar_con_llm(mensaje: str, borrador: str, traza: traza_llm.TrazaLLM | None = None) -> str:
    salida = llm_client.chat_completion(
        [{"role": "system", "content": _SISTEMA},
         {"role": "user", "content": json.dumps({"pregunta": mensaje, "borrador": borrador}, ensure_ascii=False)}],
        max_tokens=300, temperature=0.2, traza=traza,
    )  # fmt: skip
    texto = (salida.get("content") or "").strip()
    if not texto:
        if traza:
            traza.marcar("rechazada_validacion")
        raise llm_client.LLMNoDisponible("el LLM respondió vacío")
    return texto


def _historial(db, conversacion_id: str | None, limite: int = 6) -> list[dict]:
    if not conversacion_id:
        return []
    filas = db.scalars(select(m.Conversacion).where(m.Conversacion.conversacion_id == conversacion_id)
                       .order_by(m.Conversacion.fecha_hora.desc(), m.Conversacion.mensaje_id.desc())
                       .limit(limite)).all()  # fmt: skip
    rol = {RolMensaje.usuario.value: "user", RolMensaje.asistente.value: "assistant"}
    return [{"role": rol.get(getattr(f.rol, "value", f.rol), "user"), "content": f.texto} for f in reversed(filas)
            if f.texto]  # fmt: skip


def conversar_con_llm(mensaje: str, historial: list[dict], negocio: str, traza: traza_llm.TrazaLLM | None = None) -> str:
    salida = llm_client.chat_completion(
        [{"role": "system", "content": _SISTEMA_CHARLA.format(negocio=negocio)}, *historial,
         {"role": "user", "content": mensaje}],
        max_tokens=160, temperature=0.6, traza=traza,
    )  # fmt: skip
    texto = (salida.get("content") or "").strip()
    if not texto:
        if traza:
            traza.marcar("rechazada_validacion")
        raise llm_client.LLMNoDisponible("el LLM respondió vacío")
    return texto


def _nuevo_conversacion_id(db) -> str:
    numero = cast(func.substr(m.Conversacion.conversacion_id, 5), Integer)
    maximo = db.scalar(select(func.max(numero)).where(m.Conversacion.conversacion_id.op("~")(r"^CNV-[0-9]+$"))) or 0
    return f"CNV-{maximo + 1:04d}"


def _canal(canal: str) -> CanalNotificacion:
    try:
        return CanalNotificacion(canal)
    except ValueError:
        return CanalNotificacion.app


def responder(db, empresa_id: str, mensaje: str, conversacion_id: str | None = None, canal: str = "app") -> dict:
    intencion = clasificar(mensaje)
    ctx = _Contexto(db, empresa_id)
    try:
        borrador = PLANES[intencion](ctx, mensaje)
    except Exception:  # noqa: BLE001 - si una herramienta de B falla, se responde con la ayuda (sin cifras)
        log.exception("El plan del asistente falló (%s)", intencion.value)
        borrador = plantillas.Borrador("Ahora no pude revisar tus números. Intenta en un momento, por favor.")
        ctx.llamadas.clear()

    texto_plantilla = " ".join([borrador.texto, borrador.extras.get("respuesta_post", "")]).strip()
    permitidas = ctx.resultados + [{"mensaje": [float(n.valor) for n in numeros(normalizar(mensaje))]}]
    verificacion = verificador.verificar_cifras(texto_plantilla, permitidas)
    respuesta, fallback, usa_llm = borrador.texto, False, False
    traza = None
    redactar = intencion in CON_LLM and bool(ctx.llamadas)
    if redactar or borrador.conversacional:
        if settings.llm_configurado and settings.ASISTENTE_USAR_LLM:
            traza = traza_llm.crear(db, empresa_id, "asistente", PROMPT_VERSION, "mensaje")
            try:
                if redactar:
                    propuesta = redactar_con_llm(mensaje, borrador.texto, traza)
                else:
                    empresa = db.get(m.Empresa, empresa_id)
                    negocio = empresa.nombre_ficticio if empresa else "su bodega"
                    propuesta = conversar_con_llm(mensaje, _historial(db, conversacion_id), negocio, traza)
                verificacion = verificador.verificar_cifras(propuesta, permitidas)
                if verificacion["ok"] and _PROHIBIDO_LLM.search(propuesta.lower()):
                    verificacion = verificador.verificar_cifras(texto_plantilla, permitidas)
                    if traza:
                        traza.marcar("rechazada_validacion")
                    log.warning("El LLM usó porcentajes o habló de la casa; se responde la plantilla")
                    fallback = True
                elif verificacion["ok"]:
                    respuesta, usa_llm = propuesta, True
                    if traza:
                        traza.marcar("aceptada")
                else:
                    if traza:
                        traza.marcar("rechazada_verificador")
                    log.warning("Cifras no verificadas en la respuesta del LLM: %s", verificacion["no_verificadas"])
                    fallback = True
            except llm_client.LLMNoDisponible as exc:
                log.warning("Asistente sin LLM: %s", exc)
                fallback = True
        else:
            fallback = True

    conversacion_id = conversacion_id if conversacion_id and re.fullmatch(r"CNV-\d{4,12}", conversacion_id) else None
    conversacion_id = conversacion_id or _nuevo_conversacion_id(db)
    canal_n = _canal(canal)
    llamadas_publicas = [{"nombre": ll["nombre"], "args": ll["args"]} for ll in ctx.llamadas]
    fuera = intencion == I.fuera_de_alcance
    modelo, version = ("llm-openrouter", settings.LLM_MODEL) if usa_llm else ("plantillas-asistente", VERSION_PLANTILLAS)
    db.add(m.Conversacion(mensaje_id=nuevo_id(db, m.Conversacion, "MSG"), empresa_id=empresa_id,
                          conversacion_id=conversacion_id, rol=RolMensaje.usuario, canal=canal_n, texto=mensaje,
                          intencion=intencion.value, fecha_hora=ahora()))  # fmt: skip
    mensaje_asistente_id = nuevo_id(db, m.Conversacion, "MSG")
    db.add(m.Conversacion(mensaje_id=mensaje_asistente_id, empresa_id=empresa_id,
                          conversacion_id=conversacion_id, rol=RolMensaje.asistente, canal=canal_n,
                          texto=" ".join([respuesta, borrador.extras.get("respuesta_post", "")]).strip(),
                          intencion=intencion.value, herramientas_llamadas=ctx.llamadas or None,
                          cifras_verificadas=verificacion["ok"], fallback_usado=fallback,
                          derivado_a_humano=False, prompt_version=PROMPT_VERSION, modelo_version=version[:30],
                          fecha_hora=ahora()))  # fmt: skip
    if traza:
        traza.marcar(referencia_tipo="mensaje", referencia_id=mensaje_asistente_id)
    db.commit()
    return {
        "conversacion_id": conversacion_id,
        "respuesta": respuesta,
        "intencion": intencion.value,
        "herramientas_llamadas": llamadas_publicas,
        "cifras_usadas": [{"valor": v, "fuente": f} for v, f in borrador.cifras],
        "verificacion_cifras": verificacion,
        "fuera_de_alcance": fuera,
        "ofrecer_humano": borrador.ofrecer_humano,
        "disclaimer": plantillas.DISCLAIMER,
        "meta": construir_meta(modelo, version, prompt_version=PROMPT_VERSION, fallback_usado=fallback)
        .model_dump(mode="json"),
        **borrador.extras,
    }

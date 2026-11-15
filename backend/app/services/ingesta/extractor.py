"""Texto → MovimientoPropuesto (A3).

1. LLM vía OpenRouter (`llm_client.chat_completion` con una tool forzada) → salida validada con pydantic.
2. Si no hay key, hay timeout/error o la salida es inválida → extractor por reglas (`reglas.py`) y
   `fallback_usado = true`.
3. Las dos rutas pasan por la misma normalización determinística: el monto sale de lo que dijo el usuario o del
   catálogo (el LLM nunca pone precios ni suma), se calculan `campos_faltantes`, `confianza` y, si hace falta,
   `pregunta_aclaratoria` con `opciones_aclaracion`.
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.core.config import settings
from app.core.errors import NoInterpretable
from app.core.reloj import ahora, hoy
from app.schemas.common import Frecuencia, MetodoPago, OrigenMonto, TipoMovimiento, redondear
from app.services.ingesta import llm_client, reglas, traza_llm
from app.services.ingesta.catalogo import Catalogo
from app.services.ingesta.reglas import Crudo, ItemCrudo
from app.services.ingesta.texto import ResultadoFecha, fecha_corta, fecha_larga, soles, valores_en_texto

log = logging.getLogger("cajaclara.extractor")

PROMPT_VERSION = "extractor-v3"
VERSION_REGLAS = "reglas-1.0.0"
T = TipoMovimiento

MENSAJE_NO_INTERPRETABLE = 'No entendí bien. ¿Me lo dices de otra forma? Por ejemplo: "vendí 2 cervezas".'
MENSAJE_ALCANCE = ("TuCaserito solo lleva la plata del negocio, no los gastos de la casa. Si esa plata salió de la caja "
                   "de la tienda, dime cuánto fue (por ejemplo: «saqué 150 de la caja para el colegio») y lo anoto "
                   "como retiro para la casa.")  # fmt: skip


@dataclass
class Extraccion:
    movimiento: dict
    origen_monto: OrigenMonto
    confianza: float
    campos_faltantes: list[str] = field(default_factory=list)
    pregunta_aclaratoria: str | None = None
    opciones_aclaracion: list[dict] = field(default_factory=list)
    fuera_de_alcance: bool = False
    fallback_usado: bool = False
    modelo: str = "reglas-extractor"
    modelo_version: str = VERSION_REGLAS
    motivo_fallback: str | None = None
    llamada_id: str | None = None  # fila de llm_llamadas (el servicio la enlaza con el borrador)


# ── herramienta para el LLM ─────────────────────────────────────────────────────────────────────

TOOL_MOVIMIENTO = {
    "type": "function",
    "function": {
        "name": "registrar_movimiento",
        "description": "Estructura UN movimiento de dinero del negocio dicho por el dueño de la bodega.",
        "parameters": {
            "type": "object",
            "properties": {
                "es_movimiento": {"type": "boolean", "description": "false si es un saludo, una pregunta o no se entiende"},
                "es_gasto_del_hogar": {"type": "boolean",
                                       "description": "true si es un gasto de la casa (colegio, médico, etc.)"},
                "tipo": {"type": ["string", "null"], "enum": [t.value for t in TipoMovimiento] + [None]},
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "producto_id": {"type": ["string", "null"]},
                            "producto": {"type": "string"},
                            "cantidad": {"type": "number"},
                        },
                        "required": ["producto", "cantidad"],
                    },
                },
                "monto": {"type": ["number", "null"],
                          "description": "Solo si el usuario DIJO la cifra de dinero; si no, null"},
                "metodo_pago": {"type": ["string", "null"], "enum": [m.value for m in MetodoPago] + [None]},
                "contraparte": {"type": ["string", "null"], "description": "Cliente, proveedor o prestamista"},
                "fecha_vencimiento": {"type": ["string", "null"], "description": "YYYY-MM-DD"},
                "monto_total_a_pagar": {"type": ["number", "null"]},
                "frecuencia_cuota": {"type": ["string", "null"], "enum": [f.value for f in Frecuencia] + [None]},
                "monto_cuota": {"type": ["number", "null"]},
                "confianza": {"type": "number", "description": "0 a 1"},
            },
            "required": ["es_movimiento", "tipo", "confianza"],
        },
    },
}

_SISTEMA = """Eres el extractor de TuCaserito, un asistente para el dueño de una bodega en Perú. Convierte su mensaje \
en UN movimiento llamando a la función registrar_movimiento. Hoy es {hoy} (zona America/Lima).

Tipos: venta, cobro_fiado (un cliente paga lo que debía), prestamo_recibido, otro_ingreso, compra (mercadería), \
gasto_negocio (luz, agua, alquiler, mototaxi, gas, bolsas), retiro_personal (plata que el dueño saca para su casa), \
pago_proveedor, pago_prestamo, pago_impuesto (RUS, SUNAT).
Reglas:
- "le fié", "fiado", "a cuenta" → tipo venta, metodo_pago credito y contraparte = el cliente.
- "pedí X a <proveedor> para el <día>" → tipo compra, metodo_pago credito, contraparte = proveedor, \
fecha_vencimiento = ese día.
- "me pagó <cliente>" → cobro_fiado. "le pagué a <proveedor>" → pago_proveedor.
- "me prestaron X, pago Y diarios" → prestamo_recibido con monto_cuota Y y frecuencia_cuota diaria.
- Gastos de la casa (colegio, médico, ropa de los hijos) no son del negocio: es_gasto_del_hogar = true, \
tipo retiro_personal.
- NO inventes ni calcules montos: pon monto solo si el usuario dijo una cifra de dinero; si no la dijo, null \
(el sistema usa los precios de su lista). No sumes ni multipliques.
- items: productos del catálogo que se mencionan, con su producto_id y la cantidad dicha (1 si no la dice).
- Si no dice cómo pagaron, metodo_pago null. Fechas en formato YYYY-MM-DD.
- Si es un saludo, una pregunta o no es un movimiento: es_movimiento = false.
Catálogo del negocio (JSON): {catalogo}"""


class _ItemLLM(BaseModel):
    model_config = ConfigDict(extra="ignore")
    producto_id: str | None = None
    producto: str = ""
    cantidad: Decimal = Field(default=Decimal(1), gt=0, le=10000)


class SalidaLLM(BaseModel):
    model_config = ConfigDict(extra="ignore")

    es_movimiento: bool = True
    es_gasto_del_hogar: bool = False
    tipo: TipoMovimiento | None = None
    items: list[_ItemLLM] = []
    monto: Decimal | None = Field(default=None, gt=0)
    metodo_pago: MetodoPago | None = None
    contraparte: str | None = Field(default=None, max_length=100)
    fecha_vencimiento: date | None = None
    monto_total_a_pagar: Decimal | None = Field(default=None, gt=0)
    frecuencia_cuota: Frecuencia | None = None
    monto_cuota: Decimal | None = Field(default=None, gt=0)
    confianza: float = Field(default=0.9, ge=0, le=1)

    @field_validator("tipo", "metodo_pago", "frecuencia_cuota", "contraparte", "fecha_vencimiento", mode="before")
    @classmethod
    def _vacio_es_none(cls, v):
        return None if isinstance(v, str) and v.strip().lower() in ("", "null", "none") else v

    @field_validator("items", mode="before")
    @classmethod
    def _items_null(cls, v):
        return [] if v is None else v

    @field_validator("confianza", "es_movimiento", "es_gasto_del_hogar", mode="before")
    @classmethod
    def _por_defecto(cls, v, info):
        if v is None:
            return {"confianza": 0.9, "es_movimiento": True, "es_gasto_del_hogar": False}[info.field_name]
        return v


class SalidaInvalida(Exception):
    """El LLM respondió, pero sin una tool call válida."""


def _llamar_llm(texto: str, cat: Catalogo, dia: date, traza: traza_llm.TrazaLLM | None = None) -> SalidaLLM:
    sistema = _SISTEMA.format(hoy=dia.isoformat(), catalogo=json.dumps(cat.para_prompt(), ensure_ascii=False))
    mensaje = llm_client.chat_completion(
        [{"role": "system", "content": sistema}, {"role": "user", "content": texto}],
        tools=[TOOL_MOVIMIENTO],
        tool_choice={"type": "function", "function": {"name": "registrar_movimiento"}},
        max_tokens=400,
        traza=traza,
    )
    llamadas = mensaje.get("tool_calls") or []
    if not llamadas:
        if traza:
            traza.marcar("rechazada_validacion")
        raise SalidaInvalida("el LLM no llamó a la función")
    argumentos = llamadas[0].get("function", {}).get("arguments")
    try:
        datos = json.loads(argumentos) if isinstance(argumentos, str) else argumentos
        return SalidaLLM.model_validate(datos)
    except (json.JSONDecodeError, TypeError, ValidationError) as exc:
        if traza:
            traza.marcar("rechazada_validacion")
        raise SalidaInvalida(f"argumentos inválidos: {exc}") from exc


def _crudo_desde_llm(salida: SalidaLLM, texto: str, cat: Catalogo, base: Crudo) -> Crudo:
    """Mapea la salida del LLM a un Crudo. Toda cifra debe aparecer en lo que dijo el usuario."""
    dichos = valores_en_texto(texto)

    def verificado(valor: Decimal | None) -> Decimal | None:
        return valor if valor is not None and redondear(valor) in dichos else None

    tipo = T.retiro_personal if salida.es_gasto_del_hogar else salida.tipo
    # La confianza que el LLM dice de sí mismo no está calibrada: se usa el acuerdo con las reglas como señal
    # principal y la autoevaluación solo resta si el modelo duda mucho.
    confianza = 0.93 if base.tipo == tipo else 0.8
    if salida.confianza < 0.4:
        confianza -= 0.1
    crudo = Crudo(tipo=tipo, confianza=confianza, fuera_de_alcance=salida.es_gasto_del_hogar,
                  fecha=base.fecha, dias_atras=base.dias_atras)  # fmt: skip
    if tipo in (T.venta, T.compra):
        for it in salida.items:
            prod = cat.producto_por_id(it.producto_id) or (cat.buscar_producto(it.producto) if it.producto else None)
            cantidad = it.cantidad if (it.cantidad == 1 or redondear(it.cantidad) in dichos) else Decimal(1)
            crudo.items.append(ItemCrudo(prod, cantidad, prod.nombre if prod else it.producto or None))
    crudo.monto = verificado(salida.monto)
    crudo.monto_cuota = verificado(salida.monto_cuota)
    crudo.monto_total_a_pagar = verificado(salida.monto_total_a_pagar)
    crudo.frecuencia_cuota = salida.frecuencia_cuota if crudo.monto_cuota else None
    crudo.metodo_pago = salida.metodo_pago or base.metodo_pago
    if tipo == T.venta and base.metodo_pago == MetodoPago.credito:
        crudo.metodo_pago = MetodoPago.credito

    if tipo in (T.venta, T.cobro_fiado):
        crudo.cliente = cat.buscar_cliente(salida.contraparte) or base.cliente
        crudo.contraparte = crudo.cliente.nombre if crudo.cliente else (salida.contraparte or base.contraparte)
        if tipo == T.venta and crudo.metodo_pago != MetodoPago.credito:
            crudo.cliente, crudo.contraparte = None, None
    elif tipo in (T.compra, T.pago_proveedor):
        crudo.proveedor = cat.buscar_proveedor(salida.contraparte) or base.proveedor
        crudo.contraparte = crudo.proveedor.nombre if crudo.proveedor else (salida.contraparte or base.contraparte)
    elif tipo in (T.prestamo_recibido, T.pago_prestamo):
        crudo.contraparte = salida.contraparte or base.contraparte

    if crudo.fecha.fecha is None and not crudo.fecha.opciones and salida.fecha_vencimiento:
        if salida.fecha_vencimiento >= hoy():
            crudo.fecha = ResultadoFecha(salida.fecha_vencimiento, [salida.fecha_vencimiento])
    if tipo == T.gasto_negocio:
        crudo.categoria = base.categoria if base.tipo == T.gasto_negocio else None
    return crudo


# ── normalización común ─────────────────────────────────────────────────────────────────────────

_PREGUNTAS = {
    "monto": "¿De cuánto fue?",
    "contraparte": {T.venta: "¿A quién le fiaste?", T.cobro_fiado: "¿Quién te pagó?",
                    T.compra: "¿A qué proveedor le hiciste el pedido?",
                    T.pago_proveedor: "¿A qué proveedor le pagaste?"},  # fmt: skip
}


def _monto_desde_items(items: list[dict]) -> Decimal | None:
    if not items:
        return None
    return sum((Decimal(str(i["subtotal"])) for i in items), Decimal("0")) or None


def completar(crudo: Crudo, texto: str, cat: Catalogo, *, fallback: bool) -> Extraccion:
    if crudo.tipo is None:
        raise NoInterpretable(MENSAJE_NO_INTERPRETABLE)
    tipo = crudo.tipo
    faltantes: list[str] = []
    opciones: list[dict] = []
    pregunta: str | None = None
    confianza = crudo.confianza

    items = []
    for it in crudo.items:
        # Una compra se valoriza al costo del catálogo (si se conoce); una venta, al precio de venta.
        de_catalogo = None
        if it.producto:
            de_catalogo = (it.producto.costo or it.producto.precio) if tipo == T.compra else it.producto.precio
        precio = it.precio_dicho if it.precio_dicho is not None else de_catalogo
        if precio is None:
            continue
        items.append({"producto_id": it.producto.producto_id if it.producto else None,
                      "producto": it.producto.nombre if it.producto else it.nombre,
                      "cantidad": it.cantidad, "precio_unitario": redondear(precio),
                      "subtotal": redondear(it.cantidad * precio)})  # fmt: skip
    monto = crudo.monto
    if monto is not None:
        origen = OrigenMonto.dicho_por_usuario
        if len(items) == 1 and crudo.items[0].precio_dicho is None:
            items[0]["precio_unitario"] = redondear(monto / items[0]["cantidad"])
            items[0]["subtotal"] = redondear(monto)
    elif (desde_items := _monto_desde_items(items)) is not None:
        monto = desde_items
        dichos = any(it.precio_dicho is not None for it in crudo.items)
        origen = OrigenMonto.dicho_por_usuario if dichos else OrigenMonto.catalogo
    else:
        origen = OrigenMonto.estimado

    if tipo == T.cobro_fiado and monto is None and crudo.cliente and crudo.cliente.pendiente > 0:
        monto = crudo.cliente.pendiente
        origen = OrigenMonto.estimado
        faltantes.append("monto")
        opciones = [{"valor": f"{monto:.2f}", "texto": f"Sí, todo ({soles(monto)})"}]
        pregunta = f"¿{crudo.cliente.nombre} te pagó todo lo que debía ({soles(monto)})?"
    elif monto is None:
        faltantes.append("monto")

    metodo = crudo.metodo_pago or MetodoPago.efectivo
    if metodo == MetodoPago.credito and tipo not in (T.venta, T.compra):
        metodo = MetodoPago.efectivo
    credito = metodo == MetodoPago.credito

    if crudo.contraparte is None and (
        (tipo == T.venta and credito) or tipo in (T.cobro_fiado, T.pago_proveedor) or (tipo == T.compra and credito)
    ):
        faltantes.append("contraparte")

    fecha_venc: date | None = None
    if (tipo == T.compra and credito) or tipo == T.prestamo_recibido or (tipo == T.venta and credito):
        if crudo.fecha.fecha:
            fecha_venc = crudo.fecha.fecha
        elif crudo.fecha.ambigua:
            faltantes.append("fecha_vencimiento")
            opciones = [{"valor": f.isoformat(), "texto": fecha_corta(f)} for f in crudo.fecha.opciones]
            dia = crudo.fecha.opciones[0].day
            meses = " o el ".join(f"{dia} de {fecha_larga(f).split(' de ')[1]}" for f in crudo.fecha.opciones)
            pregunta = f"¿Lo pagas el {meses}?"
        elif tipo == T.compra and crudo.proveedor:
            fecha_venc = hoy() + timedelta(days=crudo.proveedor.plazo_pago_dias)
            confianza -= 0.03

    if crudo.fuera_de_alcance:
        if monto is None:
            raise NoInterpretable(MENSAJE_ALCANCE, [{"campo": "alcance", "problema": "gasto_del_hogar"}])
        faltantes = ["salio_de_caja"]
        opciones = [{"valor": "si", "texto": "Sí, salió de la caja"}, {"valor": "no", "texto": "No, fue plata de la casa"}]
        pregunta = ("TuCaserito solo lleva la plata del negocio. ¿Esa plata salió de la caja de la tienda? Si es así, "
                    "lo anoto como retiro para la casa.")  # fmt: skip
        confianza = min(confianza, 0.55)
    elif faltantes:
        confianza = min(confianza, 0.7) - 0.1 * (len(faltantes) - 1)
        if pregunta is None:
            campo = faltantes[0]
            texto_p = _PREGUNTAS.get(campo, "¿Me confirmas ese dato?")
            pregunta = texto_p.get(tipo, "¿Me confirmas ese dato?") if isinstance(texto_p, dict) else texto_p
    confianza = round(max(0.05, min(confianza, 0.99)), 3)
    if pregunta is None and confianza < settings.UMBRAL_CONFIANZA:
        pregunta = "No estoy seguro de haber entendido bien. ¿Lo anoto así?"

    fecha_hora: datetime = ahora().replace(microsecond=0) - timedelta(days=crudo.dias_atras)
    descripcion = (texto or "").strip()
    descripcion = (descripcion[:1].upper() + descripcion[1:])[:255] or None
    movimiento = {
        "tipo": tipo.value, "items": items, "monto": monto, "moneda": "PEN", "metodo_pago": metodo.value,
        "contraparte": crudo.contraparte, "fecha_hora": fecha_hora, "fecha_vencimiento": fecha_venc,
        "descripcion": descripcion,
    }  # fmt: skip
    if crudo.categoria:
        movimiento["categoria"] = crudo.categoria
    if tipo == T.prestamo_recibido:
        movimiento.update(monto_total_a_pagar=crudo.monto_total_a_pagar, monto_cuota=crudo.monto_cuota,
                          frecuencia_cuota=crudo.frecuencia_cuota.value if crudo.frecuencia_cuota else None)  # fmt: skip
    return Extraccion(
        movimiento=movimiento, origen_monto=origen, confianza=confianza, campos_faltantes=faltantes,
        pregunta_aclaratoria=pregunta if (faltantes or confianza < settings.UMBRAL_CONFIANZA) else None,
        opciones_aclaracion=opciones, fuera_de_alcance=crudo.fuera_de_alcance, fallback_usado=fallback,
    )  # fmt: skip


def extraer(texto: str, *, empresa_id: str, db=None, catalogo: Catalogo | None = None,
            usar_llm: bool = True) -> Extraccion:  # fmt: skip
    """Interpreta una frase. Lanza NoInterpretable si no hay movimiento (o si es un gasto de la casa sin monto)."""
    from app.services.ingesta import catalogo as cat_mod

    if not (texto and texto.strip()):
        raise NoInterpretable(MENSAJE_NO_INTERPRETABLE)
    cat = catalogo or cat_mod.cargar(db, empresa_id)
    dia = hoy()
    base = reglas.interpretar(texto, cat, dia)

    motivo = None
    traza = None
    if usar_llm and settings.llm_configurado:
        traza = traza_llm.crear(db, empresa_id, "extractor", PROMPT_VERSION)
        try:
            salida = _llamar_llm(texto, cat, dia, traza)
            if not salida.es_movimiento or (salida.tipo is None and not salida.es_gasto_del_hogar):
                raise NoInterpretable(MENSAJE_NO_INTERPRETABLE)
            resultado = completar(_crudo_desde_llm(salida, texto, cat, base), texto, cat, fallback=False)
            resultado.modelo, resultado.modelo_version = "llm-extractor", settings.LLM_MODEL
            if traza:
                traza.marcar("aceptada")
                resultado.llamada_id = traza.llamada_id
            return resultado
        except NoInterpretable:
            if traza:  # el modelo respondió bien; no habrá borrador ni commit, así que se confirma la traza aquí
                traza.marcar("aceptada")
                traza.confirmar()
            raise
        except (llm_client.LLMNoDisponible, SalidaInvalida) as exc:
            motivo = str(exc)
            log.warning("Extractor: uso reglas (%s)", motivo)
    else:
        motivo = "LLM sin configurar" if usar_llm else "LLM desactivado"
    resultado = completar(base, texto, cat, fallback=True)
    resultado.motivo_fallback = motivo
    resultado.llamada_id = traza.llamada_id if traza else None
    return resultado

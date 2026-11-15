"""A3/A6/A13 — extractor: fallback por reglas (offline, catálogo del seed) y ruta LLM con OpenRouter mockeado."""

import json
from datetime import date
from decimal import Decimal

import httpx
import pytest

from app.core.errors import NoInterpretable
from app.services.ingesta import catalogo, extractor
from app.services.ingesta.texto import numeros, normalizar, parsear_fecha, soles, valores_en_texto

CAT = catalogo.desde_seed()
HOY = date(2026, 11, 14)


def _extraer(texto: str):
    return extractor.extraer(texto, empresa_id="EMP-0001", catalogo=CAT)


# ── texto.py ────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(("texto", "esperado"), [
    ("pedí 2 400 a andina", [Decimal(2400)]), ("dos mil cuatrocientos", [Decimal(2400)]),
    ("me prestaron 1 000", [Decimal(1000)]), ("a 2.50 cada una", [Decimal("2.50"), Decimal(1)]), ("6,50", [Decimal("6.50")]),
    ("cuarenta y cinco soles", [Decimal(45)]), ("media docena", [Decimal(6)]), ("2 docenas", [Decimal(24)]),
    ("2 mil", [Decimal(2000)]), ("el 30/11", []), ("mil", [Decimal(1000)]),
])  # fmt: skip
def test_numeros_en_espanol(texto, esperado):
    assert [n.valor for n in numeros(normalizar(texto))] == esperado


@pytest.mark.parametrize(("texto", "fecha", "opciones"), [
    ("para el 30", None, [date(2026, 11, 30), date(2026, 12, 30)]),
    ("para el 5", date(2026, 12, 5), [date(2026, 12, 5)]),
    ("el 30 de noviembre", date(2026, 11, 30), [date(2026, 11, 30)]),
    ("30/11", date(2026, 11, 30), [date(2026, 11, 30)]),
    ("en 15 dias", date(2026, 11, 29), [date(2026, 11, 29)]),
    ("el viernes", date(2026, 11, 20), [date(2026, 11, 20)]),
    ("vendi en la manana", None, []),
])  # fmt: skip
def test_fechas(texto, fecha, opciones):
    r = parsear_fecha(normalizar(texto), HOY)
    assert r.fecha == fecha and r.opciones == opciones


def test_soles_formato():
    assert soles(Decimal("2340")) == "S/ 2 340" and soles(Decimal("13"), True) == "S/ 13.00"
    assert soles(Decimal("-650")) == "−S/ 650"


# ── fallback por reglas: frases de la demo ──────────────────────────────────────────────────────


def test_vendi_dos_cervezas_monto_por_catalogo():
    e = _extraer("vendí dos cervezas")
    mov = e.movimiento
    assert (mov["tipo"], mov["metodo_pago"], mov["monto"]) == ("venta", "efectivo", Decimal("13.00"))
    assert mov["items"] == [{"producto_id": "PRD-0031", "producto": "Cerveza 620 ml", "cantidad": Decimal(2),
                             "precio_unitario": Decimal("6.50"), "subtotal": Decimal("13.00")}]  # fmt: skip
    assert e.origen_monto == "catalogo" and e.confianza >= 0.75 and not e.campos_faltantes
    assert e.pregunta_aclaratoria is None and e.fallback_usado is True and e.modelo == "reglas-extractor"


def test_saque_100_para_la_casa():
    mov = _extraer("saqué 100 para la casa").movimiento
    assert (mov["tipo"], mov["monto"], mov["metodo_pago"]) == ("retiro_personal", Decimal(100), "efectivo")


def test_pedido_a_credito_con_dia_ambiguo():
    e = _extraer("pedí 2 400 a Andina para el 30")
    mov = e.movimiento
    assert (mov["tipo"], mov["metodo_pago"], mov["monto"], mov["contraparte"]) == (
        "compra", "credito", Decimal(2400), "Distribuidora Andina")
    assert e.campos_faltantes == ["fecha_vencimiento"] and e.confianza < 0.75
    assert e.pregunta_aclaratoria == "¿Lo pagas el 30 de noviembre o el 30 de diciembre?"
    assert e.opciones_aclaracion == [{"valor": "2026-11-30", "texto": "30/11"}, {"valor": "2026-12-30", "texto": "30/12"}]


def test_pedido_con_fecha_completa():
    e = _extraer("pedí 2400 a andina para el 30 de noviembre")
    assert e.movimiento["fecha_vencimiento"] == date(2026, 11, 30) and not e.campos_faltantes


def test_le_fie_20_a_rosa():
    e = _extraer("le fié 20 a Rosa")
    mov = e.movimiento
    assert (mov["tipo"], mov["metodo_pago"], mov["monto"], mov["contraparte"]) == (
        "venta", "credito", Decimal(20), "Vecina Rosa")
    assert e.origen_monto == "dicho_por_usuario"


def test_me_pago_rosa_sin_monto_propone_lo_pendiente():
    e = _extraer("me pagó Rosa")
    assert (e.movimiento["tipo"], e.movimiento["monto"], e.movimiento["contraparte"]) == (
        "cobro_fiado", Decimal("95.00"), "Vecina Rosa")
    assert e.origen_monto == "estimado" and e.campos_faltantes == ["monto"]
    assert e.opciones_aclaracion == [{"valor": "95.00", "texto": "Sí, todo (S/ 95)"}]


def test_pague_el_colegio_responde_alcance():
    with pytest.raises(NoInterpretable) as exc:
        _extraer("pagué el colegio de mi hijo")
    assert "solo llevo la plata del negocio" in exc.value.mensaje
    assert exc.value.detalles == [{"campo": "alcance", "problema": "gasto_del_hogar"}]


def test_pague_el_colegio_con_monto_pregunta_si_salio_de_caja():
    e = _extraer("pagué el colegio, 150")
    assert e.movimiento["tipo"] == "retiro_personal" and e.fuera_de_alcance
    assert e.campos_faltantes == ["salio_de_caja"] and e.confianza < 0.75
    assert [o["valor"] for o in e.opciones_aclaracion] == ["si", "no"]


def test_saque_para_el_colegio_es_retiro_normal():
    e = _extraer("saqué 150 de la caja para el colegio")
    assert e.movimiento["tipo"] == "retiro_personal" and not e.fuera_de_alcance and not e.campos_faltantes


@pytest.mark.parametrize(("texto", "tipo", "monto", "metodo", "contraparte"), [
    ("la señora Carmen me pagó 50", "cobro_fiado", 50, "efectivo", "Sra. Carmen"),
    ("me prestaron 1 000, pago 40 diarios", "prestamo_recibido", 1000, "efectivo", None),
    ("pagué mi RUS, 20 soles", "pago_impuesto", 20, "efectivo", None),
    ("pagué la luz, 80", "gasto_negocio", 80, "efectivo", None),
    ("le pagué 1 200 a Andina", "pago_proveedor", 1200, "efectivo", "Distribuidora Andina"),
    ("vendí 3 gaseosas a 2.50 por yape", "venta", Decimal("7.50"), "billetera_digital", None),
    ("le fié a la señora Carmen 2 panes y una leche", "venta", Decimal("4.80"), "credito", "Sra. Carmen"),
    ("compré bolsas 15 soles", "gasto_negocio", 15, "efectivo", None),
    ("pagué la cuota del préstamo, 40", "pago_prestamo", 40, "efectivo", None),
    ("me yapearon 18.50", "venta", Decimal("18.50"), "billetera_digital", None),
    ("vendí 2 cervezas por 15", "venta", 15, "efectivo", None),
])  # fmt: skip
def test_frases_tipicas(texto, tipo, monto, metodo, contraparte):
    mov = _extraer(texto).movimiento
    assert (mov["tipo"], mov["monto"], mov["metodo_pago"], mov["contraparte"]) == (tipo, Decimal(monto), metodo,
                                                                                  contraparte)


def test_prestamo_guarda_cuota_y_frecuencia():
    mov = _extraer("me prestaron 1 000, pago 40 diarios").movimiento
    assert (mov["monto_cuota"], mov["frecuencia_cuota"]) == (Decimal(40), "diaria")


def test_venta_con_precio_total_reajusta_el_item():
    item = _extraer("vendí 2 cervezas por 15").movimiento["items"][0]
    assert (item["precio_unitario"], item["subtotal"]) == (Decimal("7.50"), Decimal("15.00"))


@pytest.mark.parametrize("texto", ["hola", "¿cómo va mi caja?", "", "   "])
def test_no_interpretable(texto):
    with pytest.raises(NoInterpretable):
        _extraer(texto)


def test_monto_faltante_pide_aclaracion():
    e = _extraer("vendí un chupetín")
    assert e.campos_faltantes == ["monto"] and e.movimiento["monto"] is None
    assert e.pregunta_aclaratoria == "¿De cuánto fue?"


# ── ruta LLM (OpenRouter mockeado) ──────────────────────────────────────────────────────────────


def _tool_call(argumentos) -> dict:
    crudo = argumentos if isinstance(argumentos, str) else json.dumps(argumentos)
    return {"choices": [{"message": {"role": "assistant", "content": None, "tool_calls": [
        {"id": "call_1", "type": "function", "function": {"name": "registrar_movimiento", "arguments": crudo}}]}}]}


def test_llm_tool_call_valido(llm_falso):
    llm_falso.respuesta = _tool_call({"es_movimiento": True, "tipo": "venta", "confianza": 0.95,
                                      "items": [{"producto_id": "PRD-0031", "producto": "cerveza", "cantidad": 2}],
                                      "monto": None, "metodo_pago": None})  # fmt: skip
    e = _extraer("vendí dos cervezas")
    assert e.fallback_usado is False and e.modelo == "llm-extractor"
    assert e.movimiento["monto"] == Decimal("13.00") and e.origen_monto == "catalogo"
    enviado = llm_falso.llamadas[0]["payload"]
    assert enviado["tools"][0]["function"]["name"] == "registrar_movimiento"
    assert enviado["tool_choice"]["function"]["name"] == "registrar_movimiento"
    assert "PRD-0031" in enviado["messages"][0]["content"]


def test_llm_no_puede_inventar_montos(llm_falso):
    # El usuario no dijo 20: el monto del LLM se descarta y se usa el catálogo.
    llm_falso.respuesta = _tool_call({"es_movimiento": True, "tipo": "venta", "confianza": 0.9, "monto": 20,
                                      "items": [{"producto_id": "PRD-0031", "producto": "cerveza", "cantidad": 2}]})  # fmt: skip
    e = _extraer("vendí dos cervezas")
    assert e.movimiento["monto"] == Decimal("13.00") and e.origen_monto == "catalogo"


def test_llm_pedido_a_credito_con_fecha(llm_falso):
    llm_falso.respuesta = _tool_call({"es_movimiento": True, "tipo": "compra", "metodo_pago": "credito",
                                      "contraparte": "Andina", "monto": 2400, "fecha_vencimiento": "2026-11-30",
                                      "confianza": 0.9})  # fmt: skip
    e = _extraer("pedí 2 400 a Andina para el 30 de noviembre")
    mov = e.movimiento
    assert (mov["tipo"], mov["metodo_pago"], mov["contraparte"], mov["fecha_vencimiento"]) == (
        "compra", "credito", "Distribuidora Andina", date(2026, 11, 30))
    assert e.fallback_usado is False


def test_llm_items_null_y_confianza_baja_no_rompen(llm_falso):
    # Visto en el smoke test real: gpt-4o-mini mandó "items": null y una autoconfianza de 0.5.
    llm_falso.respuesta = _tool_call({"es_movimiento": True, "tipo": "compra", "metodo_pago": "credito", "items": None,
                                      "contraparte": "Distribuidora Andina", "monto": 2400, "confianza": None})  # fmt: skip
    e = _extraer("pedí 2400 a Andina para el 30")
    assert e.fallback_usado is False and e.movimiento["contraparte"] == "Distribuidora Andina"
    llm_falso.respuesta = _tool_call({"es_movimiento": True, "tipo": "venta", "confianza": 0.5,
                                      "items": [{"producto_id": "PRD-0031", "producto": "cerveza", "cantidad": 2}]})  # fmt: skip
    e = _extraer("vendí dos cervezas")
    assert e.confianza >= 0.75 and e.pregunta_aclaratoria is None


def test_llm_dia_ambiguo_igual_pregunta(llm_falso):
    llm_falso.respuesta = _tool_call({"es_movimiento": True, "tipo": "compra", "metodo_pago": "credito",
                                      "contraparte": "Distribuidora Andina", "monto": 2400,
                                      "fecha_vencimiento": "2026-11-30", "confianza": 0.95})  # fmt: skip
    e = _extraer("pedí 2400 a andina para el 30")
    assert e.campos_faltantes == ["fecha_vencimiento"] and len(e.opciones_aclaracion) == 2


# Respuestas reales e inestables del LLM para el mismo pedido: 2400, un producto al costo (3.5), null y el día (30).
_PEDIDO_BASE = {"es_movimiento": True, "tipo": "compra", "metodo_pago": "credito", "contraparte": "Andina",
                "confianza": 0.9}  # fmt: skip


@pytest.mark.parametrize("texto", ["pedi 2400 a andina para el 30", "pedí 2 400 a Andina para pagar el 30",
                                   "pedí 2400 a andina para el 30", "pedí 2,400 a Andina para el 30",
                                   "pedí dos mil cuatrocientos a Andina para el 30"])  # fmt: skip
@pytest.mark.parametrize("salida_llm", [
    {"monto": 2400},
    {"monto": None, "items": [{"producto_id": "PRD-0022", "producto": "leche", "cantidad": 1}]},
    {"monto": None},
    {"monto": 30},
], ids=["2400", "item_3.5", "null", "dia_30"])  # fmt: skip
def test_llm_monto_del_pedido_es_deterministico(llm_falso, texto, salida_llm):
    llm_falso.respuesta = _tool_call({**_PEDIDO_BASE, **salida_llm})
    e = _extraer(texto)
    mov = e.movimiento
    assert e.fallback_usado is False
    assert (mov["tipo"], mov["metodo_pago"], mov["monto"], mov["items"]) == ("compra", "credito", Decimal(2400), [])
    assert e.origen_monto == "dicho_por_usuario" and e.campos_faltantes == ["fecha_vencimiento"]


def test_llm_no_inventa_monto_si_no_hay_cifra(llm_falso):
    # Sin cifra de dinero en el texto el monto sale del catálogo, aunque el modelo proponga uno.
    llm_falso.respuesta = _tool_call({"es_movimiento": True, "tipo": "venta", "confianza": 0.9, "monto": 2,
                                      "items": [{"producto_id": "PRD-0031", "producto": "cerveza", "cantidad": 2}]})  # fmt: skip
    e = _extraer("vendí 2 cervezas")
    assert e.movimiento["monto"] == Decimal("13.00") and e.origen_monto == "catalogo"


def test_llm_respeta_precio_unitario_dicho(llm_falso):
    llm_falso.respuesta = _tool_call({"es_movimiento": True, "tipo": "venta", "confianza": 0.9, "monto": 6,
                                      "items": [{"producto_id": "PRD-0031", "producto": "cerveza", "cantidad": 2}]})  # fmt: skip
    e = _extraer("vendí 2 cervezas a 6")
    assert e.movimiento["monto"] == Decimal("12.00") and e.movimiento["items"][0]["precio_unitario"] == Decimal("6.00")


def test_llm_venta_no_es_fiado_si_no_lo_dice(llm_falso):
    llm_falso.respuesta = _tool_call({"es_movimiento": True, "tipo": "venta", "confianza": 0.5, "metodo_pago": "credito",
                                      "items": [{"producto_id": "PRD-0031", "producto": "cerveza", "cantidad": 2}]})  # fmt: skip
    e = _extraer("vendí dos cervezas")
    assert e.movimiento["metodo_pago"] == "efectivo" and e.campos_faltantes == []


def test_llm_gasto_del_hogar(llm_falso):
    llm_falso.respuesta = _tool_call({"es_movimiento": True, "es_gasto_del_hogar": True, "tipo": None, "confianza": 0.9})
    with pytest.raises(NoInterpretable, match="solo llevo la plata del negocio"):
        _extraer("pagué el colegio de mi hija")


def test_llm_no_es_movimiento(llm_falso):
    llm_falso.respuesta = _tool_call({"es_movimiento": False, "tipo": None, "confianza": 0.9})
    with pytest.raises(NoInterpretable):
        _extraer("hola, buenos días")


@pytest.mark.parametrize("respuesta", [
    _tool_call("{esto no es json"),
    _tool_call({"es_movimiento": True, "tipo": "regalo", "confianza": 0.9}),
    _tool_call({"es_movimiento": True, "tipo": "venta", "confianza": 7}),
    {"choices": [{"message": {"role": "assistant", "content": "Es una venta de 13 soles"}}]},
], ids=["json_invalido", "tipo_invalido", "confianza_fuera_de_rango", "sin_tool_call"])  # fmt: skip
def test_llm_salida_invalida_usa_reglas(llm_falso, respuesta):
    llm_falso.respuesta = respuesta
    e = _extraer("vendí dos cervezas")
    assert e.fallback_usado is True and e.movimiento["monto"] == Decimal("13.00")
    assert len(llm_falso.llamadas) == 1


@pytest.mark.parametrize("error", [httpx.ReadTimeout("lento"), httpx.ConnectError("sin red")], ids=["timeout", "red"])
def test_llm_caido_usa_reglas(llm_falso, error):
    llm_falso.error = error
    e = _extraer("saqué 100 para la casa")
    assert e.fallback_usado is True and e.movimiento["tipo"] == "retiro_personal"
    assert "no respondió" in e.motivo_fallback or "red" in e.motivo_fallback


def test_sin_key_no_llama_al_llm():
    e = _extraer("vendí dos cervezas")
    assert e.fallback_usado is True and e.motivo_fallback == "LLM sin configurar"


def test_valores_en_texto():
    assert valores_en_texto("pedí 2 400 a andina para el 30") == {Decimal("2400.00"), Decimal("30.00")}


# ── A13: set de evaluación (regresión de exactitud del fallback por reglas) ─────────────────────


def test_eval_extractor_reglas_supera_umbral():
    from tests import eval_extractor

    resultado = eval_extractor.evaluar(usar_llm=False)
    assert resultado["n"] >= 100
    assert resultado["exactitud_por_campo"]["tipo"] >= 0.9
    assert resultado["exactitud_total"] >= 0.8


def test_llm_no_cambia_el_producto_nombrado(llm_falso):
    # "gaseosas" está en el catálogo: si el LLM elige otro producto (agua), mandan las reglas.
    from app.db.seed_demo import PRODUCTO_ID

    llm_falso.respuesta = _tool_call({"es_movimiento": True, "tipo": "venta", "confianza": 0.9,
                                      "items": [{"producto_id": PRODUCTO_ID["Agua 625 ml"], "producto": "agua", "cantidad": 3}]})  # fmt: skip
    e = _extraer("vendí 3 gaseosas")
    assert [i["producto"] for i in e.movimiento["items"]] == ["Gaseosa 500 ml"]
    assert e.movimiento["monto"] == Decimal("7.50")

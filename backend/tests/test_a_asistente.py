"""A8/A10 — asistente: intenciones, herramientas de B, verificador de cifras, plantillas y `conversaciones`."""

import pytest

from app.core.config import settings
from app.db import models as m
from app.services.asistente import orquestador, plantillas, verificador
from app.services.asistente.orquestador import clasificar

P = settings.API_PREFIX
EMP = f"{P}/empresas/EMP-0001"
CLAVES = {"conversacion_id", "respuesta", "intencion", "herramientas_llamadas", "cifras_usadas", "verificacion_cifras",
          "fuera_de_alcance", "ofrecer_humano", "disclaimer", "meta"}  # fmt: skip


@pytest.mark.parametrize(("mensaje", "intencion"), [
    ("¿cómo va mi caja?", "estado_caja"), ("cuánto tengo", "estado_caja"),
    ("¿Por qué me va a faltar plata a fin de mes?", "explicar_alerta"), ("¿me alcanza para el 30?", "explicar_alerta"),
    ("¿y si pago en 2 partes?", "simular"), ("y si pido 1800", "simular"), ("¿y si cobro los fiados?", "simular"),
    ("y si pido un préstamo?", "prestamo"), ("¿me conviene el gota a gota?", "prestamo"),
    ("¿qué banco me presta más barato?", "fuera_de_alcance"), ("¿invierto en bitcoin?", "fuera_de_alcance"),
    ("¿tengo que pagar IGV?", "fuera_de_alcance"), ("¿qué es el flujo de caja?", "concepto"),
    ("quiero ponerme un sueldo fijo", "crear_meta"), ("hola", "otro"),
])  # fmt: skip
def test_clasificar(mensaje, intencion):
    assert clasificar(mensaje).value == intencion


# ── verificador ──


def test_verificador_acepta_cifras_de_las_herramientas():
    datos = [{"saldo": 2340.0, "dia_critico": {"saldo_p50": -650.0}, "monto": 2400}]
    texto = "Hoy tienes S/ 2 340. El 30/11 pagas S/ 2 400 y te faltarían −S/ 650 en 2 partes."
    assert verificador.verificar_cifras(texto, datos) == {"ok": True, "no_verificadas": []}


def test_verificador_rechaza_cifras_inventadas():
    r = verificador.verificar_cifras("Tienes S/ 2 340 y te sobran S/ 1 234.50.", [{"saldo": 2340.0}])
    assert r == {"ok": False, "no_verificadas": [1234.5]}


def test_verificador_ignora_fechas_y_conteos():
    assert verificador.verificar_cifras("El 30 de noviembre, en 3 cuotas, el 15/12.", [])["ok"] is True


# ── endpoint (plantillas, sin LLM) ──


@pytest.mark.db
def test_estado_caja_con_plantilla(client_db, db):
    r = client_db.post(f"{EMP}/asistente/mensajes", json={"mensaje": "¿cómo va mi caja?", "canal": "app"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert CLAVES <= set(d) and d["intencion"] == "estado_caja"
    assert d["respuesta"].startswith("Hoy tienes S/ 2 340 en la caja del negocio.")
    assert "te faltarían S/ 650" in d["respuesta"]
    assert [h["nombre"] for h in d["herramientas_llamadas"]] == ["obtener_resumen", "obtener_forecast"]
    assert {"valor": 2340.0, "fuente": "resumen.indicadores.saldo_caja_negocio"} in d["cifras_usadas"]
    assert d["verificacion_cifras"]["ok"] is True and d["meta"]["fallback_usado"] is True  # sin LLM → plantilla
    assert d["tabla"][0] == {"etiqueta": "Caja del negocio", "valor": 2340.0}
    filas = db.query(m.Conversacion).filter_by(conversacion_id=d["conversacion_id"]).order_by(m.Conversacion.mensaje_id).all()
    assert [f.rol for f in filas] == ["usuario", "asistente"]
    assert filas[1].cifras_verificadas is True and filas[1].fallback_usado is True and filas[1].herramientas_llamadas


@pytest.mark.db
def test_explicar_alerta_con_causas_y_simulacion(client_db):
    d = client_db.post(f"{EMP}/asistente/mensajes",
                       json={"conversacion_id": "CNV-0031", "mensaje": "¿Por qué me va a faltar plata?"}).json()  # fmt: skip
    assert d["conversacion_id"] == "CNV-0031" and d["intencion"] == "explicar_alerta"
    assert "S/ 700" in d["respuesta"] and "S/ 310" in d["respuesta"]
    assert "Si pides S/ 1 800 y pagas en 2 partes, el 30/11 tendrías S/ 850." in d["respuesta"]
    nombres = [h["nombre"] for h in d["herramientas_llamadas"]]
    assert nombres[0] == "obtener_alertas" and "simular" in nombres
    assert d["ofrecer_humano"] is True and d["verificacion_cifras"]["ok"] is True


@pytest.mark.db
def test_simular_en_dos_partes(client_db):
    d = client_db.post(f"{EMP}/asistente/mensajes", json={"mensaje": "¿y si pago en 2 partes?"}).json()
    assert d["intencion"] == "simular" and d["respuesta"].startswith("Si pagas en 2 partes, el 30/11")
    assert "tendrías S/ 550" in d["respuesta"] and "(sin cambios: −S/ 650)" in d["respuesta"]
    simular = next(h for h in d["herramientas_llamadas"] if h["nombre"] == "simular")
    assert simular["args"]["acciones"] == [{"tipo": "pagar_en_partes", "pedido_id": "PED-0012", "partes": 2}]


@pytest.mark.db
def test_prestamo_muestra_costo_y_alternativas(client_db):
    d = client_db.post(f"{EMP}/asistente/mensajes", json={"mensaje": "y si pido un préstamo?"}).json()
    assert d["intencion"] == "prestamo" and d["fuera_de_alcance"] is False and d["ofrecer_humano"] is True
    assert d["ejemplo_prestamo_informal"] == {"recibes": 1000, "devuelves": 1200, "dias": 30, "cuota_diaria": 40}
    assert "te cuesta S/ 200 más en solo 30 días, pagando S/ 40 cada día" in d["respuesta_post"]
    assert "%" not in d["respuesta"] + d["respuesta_post"]
    assert [a["tipo"] for a in d["acciones"]] == ["abrir_simulador", "hablar_humano"]
    assert d["meta"]["fallback_usado"] is False and d["verificacion_cifras"]["ok"] is True


@pytest.mark.db
def test_fuera_de_alcance(client_db):
    d = client_db.post(f"{EMP}/asistente/mensajes", json={"mensaje": "¿qué banco me recomiendas para un crédito?"}).json()
    assert d["intencion"] == "fuera_de_alcance" and d["fuera_de_alcance"] is True and d["ofrecer_humano"] is True
    assert d["herramientas_llamadas"] == [] and "no recomiendo créditos" in d["respuesta"]


# ── ruta LLM mockeada ──


def _respuesta_llm(texto: str) -> dict:
    return {"choices": [{"message": {"role": "assistant", "content": texto}}]}


@pytest.mark.db
def test_llm_redacta_con_cifras_verificadas(client_db, llm_falso):
    llm_falso.respuesta = _respuesta_llm("¡Hola! Tienes S/ 2 340 en caja; el 30/11 te faltarían S/ 650 para Andina.")
    d = client_db.post(f"{EMP}/asistente/mensajes", json={"mensaje": "¿cómo va mi caja?"}).json()
    assert d["respuesta"].startswith("¡Hola! Tienes S/ 2 340")
    assert d["meta"]["fallback_usado"] is False and d["meta"]["modelo"] == "llm-openrouter"
    assert d["verificacion_cifras"]["ok"] is True
    enviado = llm_falso.llamadas[0]["payload"]
    assert "tools" not in enviado and "BORRADOR" in enviado["messages"][0]["content"]


@pytest.mark.db
def test_llm_con_cifra_inventada_se_reemplaza_por_plantilla(client_db, llm_falso, db):
    llm_falso.respuesta = _respuesta_llm("Tienes S/ 2 340 y el 30/11 te sobrarán S/ 4 321.")
    d = client_db.post(f"{EMP}/asistente/mensajes", json={"mensaje": "¿cómo va mi caja?"}).json()
    assert d["respuesta"].startswith("Hoy tienes S/ 2 340 en la caja del negocio.")
    assert d["verificacion_cifras"] == {"ok": False, "no_verificadas": [4321.0]}
    assert d["meta"]["fallback_usado"] is True
    fila = db.query(m.Conversacion).filter_by(conversacion_id=d["conversacion_id"], rol="asistente").one()
    assert fila.cifras_verificadas is False and fila.fallback_usado is True


@pytest.mark.db
def test_llm_caido_usa_plantilla(client_db, llm_falso):
    import httpx

    llm_falso.error = httpx.ReadTimeout("lento")
    d = client_db.post(f"{EMP}/asistente/mensajes", json={"mensaje": "¿cómo va mi caja?"}).json()
    assert d["meta"]["fallback_usado"] is True and d["respuesta"].startswith("Hoy tienes S/ 2 340")


@pytest.mark.db
def test_prestamo_no_pasa_por_el_llm(client_db, llm_falso):
    client_db.post(f"{EMP}/asistente/mensajes", json={"mensaje": "¿y si pido un préstamo?"})
    assert llm_falso.llamadas == []


@pytest.mark.db
def test_herramienta_que_falla_responde_sin_cifras(client_db, monkeypatch):
    from app.services.asistente import herramientas

    def _roto(*_a, **_k):
        raise RuntimeError("B caído")

    monkeypatch.setattr(herramientas, "ejecutar", _roto)
    d = client_db.post(f"{EMP}/asistente/mensajes", json={"mensaje": "¿cómo va mi caja?"}).json()
    assert "no pude revisar" in d["respuesta"].lower() and d["cifras_usadas"] == []


def test_responder_existe():
    assert orquestador.PROMPT_VERSION == "asistente-v3"


# ── charla (intención otro): natural, sin menú fijo ──


@pytest.mark.db
@pytest.mark.parametrize(("mensaje", "inicio"), [
    ("hola", "¡Hola!"), ("muchas gracias", "¡De nada!"), ("chau", "¡Cuídate!"), ("mmm no sé", "Cuéntame"),
])  # fmt: skip
def test_otro_sin_llm_responde_natural(client_db, mensaje, inicio):
    d = client_db.post(f"{EMP}/asistente/mensajes", json={"mensaje": mensaje}).json()
    assert d["intencion"] == "otro" and d["respuesta"].startswith(inicio)
    assert "Puedo ayudarte con:" not in d["respuesta"] and d["herramientas_llamadas"] == []


@pytest.mark.db
def test_otro_con_llm_charla_dentro_del_alcance(client_db, llm_falso):
    llm_falso.respuesta = _respuesta_llm("¡Hola, Pedro! Todo bien por aquí. ¿Revisamos cómo va tu caja?")
    d = client_db.post(f"{EMP}/asistente/mensajes", json={"mensaje": "hola, qué tal"}).json()
    assert d["respuesta"] == "¡Hola, Pedro! Todo bien por aquí. ¿Revisamos cómo va tu caja?"
    assert d["meta"]["fallback_usado"] is False and d["meta"]["modelo"] == "llm-openrouter"
    sistema = llm_falso.llamadas[0]["payload"]["messages"][0]["content"]
    assert "porcentajes" in sistema and "la casa" in sistema and "vecino" in sistema
    assert "Bodega Don Pedro" in sistema


@pytest.mark.db
def test_otro_con_llm_que_inventa_cifras_o_dice_casa_usa_plantilla(client_db, llm_falso):
    llm_falso.respuesta = _respuesta_llm("¡Hola! Hoy tienes S/ 2 340 en caja.")
    d = client_db.post(f"{EMP}/asistente/mensajes", json={"mensaje": "hola"}).json()
    assert d["respuesta"] == plantillas.SALUDO and d["meta"]["fallback_usado"] is True
    llm_falso.respuesta = _respuesta_llm("¡Hola! Recuerda separar la plata de la casa.")
    d = client_db.post(f"{EMP}/asistente/mensajes", json={"mensaje": "hola"}).json()
    assert d["respuesta"] == plantillas.SALUDO and d["meta"]["fallback_usado"] is True


@pytest.mark.db
def test_otro_con_llm_recibe_el_historial(client_db, llm_falso):
    llm_falso.respuesta = _respuesta_llm("¡Con gusto!")
    primero = client_db.post(f"{EMP}/asistente/mensajes", json={"mensaje": "hola"}).json()
    client_db.post(f"{EMP}/asistente/mensajes", json={"mensaje": "gracias", "conversacion_id": primero["conversacion_id"]})
    mensajes = llm_falso.llamadas[-1]["payload"]["messages"]
    assert [x["role"] for x in mensajes] == ["system", "user", "assistant", "user"]
    assert mensajes[1]["content"] == "hola" and mensajes[-1]["content"] == "gracias"


def test_textos_sin_casa_ni_porcentajes():
    textos = [*plantillas.MICROEXPLICACIONES.values(), plantillas.AYUDA, plantillas.SALUDO, plantillas.GRACIAS]
    assert not any("casa" in t.lower() or "%" in t for t in textos)
    for sistema in (orquestador._SISTEMA, orquestador._SISTEMA_CHARLA):
        assert "porcentajes" in sistema and "la casa" in sistema

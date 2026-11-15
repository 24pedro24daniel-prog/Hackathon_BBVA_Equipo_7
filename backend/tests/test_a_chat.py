"""POST /empresas/{id}/chat/mensajes: registro, corrección, respuesta a la pregunta, confirmación, cancelación y
asistente, con reglas (sin LLM) y con el clasificador LLM mockeado."""

import json

import httpx
import pytest

from app.core.config import settings
from app.db import models as m
from app.services.ingesta import llm_client

pytestmark = pytest.mark.db
P = settings.API_PREFIX
URL = f"{P}/empresas/EMP-0001/chat/mensajes"


def _chat(cliente, texto, borrador_id=None, **extra):
    r = cliente.post(URL, json={"texto": texto, "borrador_id": borrador_id, **extra})
    assert r.status_code == 200, r.text
    return r.json()


def _bid(r):
    return r["interpretacion"]["borrador_id"]


def test_venta_corregir_y_confirmar(client_db, db):
    r = _chat(client_db, "vendí dos cervezas")
    assert r["tipo"] == "registro" and r["mensaje"] and r["interpretacion"]["movimiento_propuesto"]["monto"] == 13.0
    bid = _bid(r)
    corr = _chat(client_db, "fue por billetera", bid)
    assert corr["tipo"] == "borrador_actualizado" and _bid(corr) == bid
    assert corr["interpretacion"]["movimiento_propuesto"]["metodo_pago"] == "billetera_digital"
    assert "billetera" in corr["mensaje"]
    ok = _chat(client_db, "sí", bid)
    assert ok["tipo"] == "guardado" and ok["confirmacion"]["movimiento_id"] and "anotado" in ok["mensaje"]
    tx = db.query(m.Transaccion).filter_by(borrador_id=bid).one()
    assert tx.metodo_pago == "billetera_digital" and tx.fue_corregida is True


def test_pedido_responde_fecha_muestra_chequeo_y_guarda(client_db, db):
    r = _chat(client_db, "pedí 2400 a andina para el 30")
    interp = r["interpretacion"]
    assert r["tipo"] == "registro" and interp["movimiento_propuesto"]["monto"] == 2400.0
    assert interp["campos_faltantes"] == ["fecha_vencimiento"] and len(interp["opciones_aclaracion"]) == 2
    assert r["mensaje"] == "¿Lo pagas el 30 de noviembre o el 30 de diciembre?"
    bid = _bid(r)
    upd = _chat(client_db, "el 30 de noviembre", bid)
    assert upd["tipo"] == "borrador_actualizado" and upd["interpretacion"]["campos_faltantes"] == []
    assert upd["interpretacion"]["movimiento_propuesto"]["fecha_vencimiento"] == "2026-11-30"
    assert upd["interpretacion"]["chequeo_pedido"]["fecha_vencimiento"] == "2026-11-30"
    ok = _chat(client_db, "dale", bid)
    assert ok["tipo"] == "guardado"
    assert db.query(m.Deuda).filter_by(borrador_id=bid).one().fecha_vencimiento.isoformat() == "2026-11-30"


@pytest.mark.parametrize("respuesta", ["noviembre", "este mes", "30"])
def test_pedido_respuestas_cortas_a_la_fecha(client_db, respuesta):
    bid = _bid(_chat(client_db, "pedí 2 400 a Andina para pagar el 30"))
    upd = _chat(client_db, respuesta, bid)
    assert upd["tipo"] == "borrador_actualizado"
    assert upd["interpretacion"]["movimiento_propuesto"]["fecha_vencimiento"] == "2026-11-30"
    assert upd["interpretacion"]["movimiento_propuesto"]["monto"] == 2400.0


def test_responder_el_monto_guarda_de_una(client_db, db):
    r = _chat(client_db, "vendí un chupetín")
    assert r["interpretacion"]["campos_faltantes"] == ["monto"] and r["mensaje"] == "¿De cuánto fue?"
    ok = _chat(client_db, "1.50", _bid(r))
    assert ok["tipo"] == "guardado"
    assert db.query(m.Transaccion).filter_by(borrador_id=_bid(r)).one().monto == 1.5


def test_eran_tres_cambia_la_cantidad(client_db):
    bid = _bid(_chat(client_db, "vendí dos cervezas"))
    upd = _chat(client_db, "eran 3", bid)
    mov = upd["interpretacion"]["movimiento_propuesto"]
    assert upd["tipo"] == "borrador_actualizado" and mov["monto"] == 19.5 and float(mov["items"][0]["cantidad"]) == 3


def test_no_15_soles_cambia_el_monto(client_db):
    bid = _bid(_chat(client_db, "vendí dos cervezas"))
    upd = _chat(client_db, "no, 15 soles", bid)
    assert upd["tipo"] == "borrador_actualizado" and upd["interpretacion"]["movimiento_propuesto"]["monto"] == 15.0
    assert upd["interpretacion"]["origen_monto"] == "dicho_por_usuario"


def test_cancelar(client_db, db):
    bid = _bid(_chat(client_db, "vendí dos cervezas"))
    r = _chat(client_db, "no, bórralo", bid)
    assert r["tipo"] == "descartado" and r["mensaje"]
    assert db.get(m.Borrador, bid).estado == "descartado"


def test_preguntas_y_charla_van_al_asistente(client_db):
    r = _chat(client_db, "como va mi caja?")
    assert r["tipo"] == "asistente" and r["asistente"]["respuesta"] and r["mensaje"]
    assert r["conversacion_id"] == r["asistente"]["conversacion_id"]
    g = _chat(client_db, "gracias!", conversacion_id=r["conversacion_id"])
    assert g["tipo"] == "asistente" and g["mensaje"] and g["conversacion_id"] == r["conversacion_id"]


def test_mensaje_no_interpretable_va_al_asistente(client_db):
    r = _chat(client_db, "qwerty asdf")
    assert r["tipo"] == "asistente" and r["mensaje"]


def test_gasto_personal_sin_monto_explica(client_db):
    r = _chat(client_db, "pagué el colegio de mi hijo")
    assert r["tipo"] == "asistente" and "solo llevo la plata del negocio" in r["mensaje"] and "casa" not in r["mensaje"]


def test_pregunta_con_borrador_pendiente_no_lo_toca(client_db, db):
    bid = _bid(_chat(client_db, "vendí dos cervezas"))
    r = _chat(client_db, "¿cuánto tengo en caja?", bid)
    assert r["tipo"] == "asistente" and db.get(m.Borrador, bid).estado == "pendiente"


def test_movimiento_nuevo_con_borrador_pendiente(client_db, db):
    bid = _bid(_chat(client_db, "pedí 2400 a andina para el 30"))
    r = _chat(client_db, "saqué 50 de la caja", bid)
    assert r["tipo"] == "registro" and _bid(r) != bid
    assert r["interpretacion"]["movimiento_propuesto"]["tipo"] == "retiro_personal"
    assert db.get(m.Borrador, bid).estado == "pendiente"


def test_borrador_resuelto_se_ignora(client_db):
    bid = _bid(_chat(client_db, "vendí dos cervezas"))
    assert _chat(client_db, "sí", bid)["tipo"] == "guardado"
    assert _chat(client_db, "vendí 3 cervezas", bid)["tipo"] == "registro"


def test_confirmar_por_ingesta_respeta_correcciones_del_chat(client_db, db):
    bid = _bid(_chat(client_db, "vendí dos cervezas"))
    _chat(client_db, "fue por yape", bid)
    assert client_db.post(f"{P}/ingesta/confirmar", json={"borrador_id": bid}).status_code == 201
    assert db.query(m.Transaccion).filter_by(borrador_id=bid).one().metodo_pago == "billetera_digital"


def test_voz(client_db, whisper_falso):
    r = _chat(client_db, "vendí dos cervezas", canal="voz", media_url="demo://audios/vendi_dos_cervezas.ogg")
    assert r["tipo"] == "registro" and r["transcripcion"] == "vendí dos cervezas"


def test_errores(client_db):
    assert client_db.post(URL, json={"texto": "  "}).status_code == 400
    assert client_db.post(f"{P}/empresas/EMP-9999/chat/mensajes", json={"texto": "hola"}).status_code == 404


# ── clasificador LLM (solo cuando las reglas dudan) ─────────────────────────────────────────────


def _tool(nombre: str, args: dict) -> dict:
    return {"choices": [{"message": {"role": "assistant", "content": None, "tool_calls": [
        {"id": "c1", "type": "function", "function": {"name": nombre, "arguments": json.dumps(args)}}]}}]}  # fmt: skip


@pytest.fixture
def llm_chat(monkeypatch, llm_falso):
    """Responde según la tool que se pidió: clasificar_mensaje → `clasificacion`; el extractor → error (usa reglas)."""
    llm_falso.clasificacion = {"accion": "corregir"}

    def _post(url, payload, headers, timeout):
        nombre = payload["tool_choice"]["function"]["name"]
        llm_falso.llamadas.append(nombre)
        if llm_falso.error is not None:
            raise llm_falso.error
        if nombre == "clasificar_mensaje":
            return _tool(nombre, llm_falso.clasificacion)
        raise httpx.ConnectError("extractor sin red en este test")

    monkeypatch.setattr(llm_client, "_post", _post)
    return llm_falso


def test_llm_resuelve_lo_ambiguo(client_db, llm_chat):
    bid = _bid(_chat(client_db, "vendí dos cervezas"))
    llm_chat.llamadas.clear()
    llm_chat.clasificacion = {"accion": "corregir", "cantidad": 3}
    upd = _chat(client_db, "vendí 3, no 2", bid)
    assert llm_chat.llamadas == ["clasificar_mensaje"]
    assert upd["tipo"] == "borrador_actualizado" and upd["interpretacion"]["movimiento_propuesto"]["monto"] == 19.5
    assert upd["meta"]["modelo"] == "llm-chat"


def test_llm_no_se_llama_si_las_reglas_estan_seguras(client_db, llm_chat):
    bid = _bid(_chat(client_db, "vendí dos cervezas"))
    llm_chat.llamadas.clear()
    assert _chat(client_db, "fue por billetera", bid)["tipo"] == "borrador_actualizado"
    assert _chat(client_db, "ya", bid)["tipo"] == "guardado"
    assert llm_chat.llamadas == []


def test_llm_no_inventa_cifras_en_la_correccion(client_db, llm_chat):
    bid = _bid(_chat(client_db, "vendí dos cervezas"))
    llm_chat.clasificacion = {"accion": "corregir", "monto": 99}
    upd = _chat(client_db, "mejor ponle lo de siempre", bid)
    assert upd["tipo"] == "borrador_actualizado" and upd["interpretacion"]["movimiento_propuesto"]["monto"] == 13.0


def test_llm_caido_usa_reglas(client_db, llm_chat):
    bid = _bid(_chat(client_db, "vendí dos cervezas"))
    llm_chat.error = httpx.ConnectError("sin red")
    r = _chat(client_db, "vendí 3 cervezas más", bid)
    assert r["tipo"] == "registro" and _bid(r) != bid and r["meta"]["fallback_usado"] is True

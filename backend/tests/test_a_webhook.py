"""A7 — POST /webhooks/whatsapp: enrutamiento, registro con botones, corrección, pedido, cuaderno, preguntas."""

import hashlib

import pytest

from app.core.config import settings
from app.db import models as m

pytestmark = pytest.mark.db
P = settings.API_PREFIX
HASH_PEDRO = hashlib.sha256(b"+51900000001").hexdigest()


def _wa(cliente, tipo="texto", texto=None, **extra):
    body = {"telefono_hash": extra.pop("telefono_hash", "a91f"), "empresa_id": "EMP-0001", "tipo": tipo,
            "texto": texto, **extra}  # fmt: skip
    r = cliente.post(f"{P}/webhooks/whatsapp", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def _boton(respuesta, prefijo):
    return next(b["id"] for b in respuesta["botones"] if b["id"].startswith(prefijo))


def test_texto_registra_borrador_con_botones(client_db):
    r = _wa(client_db, texto="vendí dos cervezas")
    assert r["respuesta_texto"] == "Anotado: 2 Cerveza 620 ml, S/ 13.00, efectivo ✅ ¿Correcto?"
    assert [b["texto"] for b in r["botones"]] == ["✅ Correcto", "✏️ Corregir"]
    assert r["respuesta_audio_url"] is None


def test_boton_confirmar_guarda(client_db, db):
    r = _wa(client_db, texto="saqué 50 para la casa")
    bid = _boton(r, "confirmar:").split(":")[1]
    ok = _wa(client_db, tipo="boton", texto=f"confirmar:{bid}")
    assert ok["respuesta_texto"].startswith("Listo, quedó anotado ✅") and "Caja del negocio hoy" in ok["respuesta_texto"]
    assert db.query(m.Transaccion).filter_by(borrador_id=bid).count() == 1
    again = _wa(client_db, tipo="boton", texto=f"confirmar:{bid}")
    assert "ya estaba resuelto" in again["respuesta_texto"]


def test_corregir_y_luego_texto_aplica_la_correccion(client_db, db):
    r = _wa(client_db, texto="vendí dos cervezas")
    bid = _boton(r, "corregir:").split(":")[1]
    assert "¿qué le cambio?" in _wa(client_db, tipo="boton", texto=f"corregir:{bid}")["respuesta_texto"]
    corr = _wa(client_db, texto="fue por billetera")
    assert corr["respuesta_texto"].startswith("Corregido:") and "billetera" in corr["respuesta_texto"]
    _wa(client_db, tipo="boton", texto=_boton(corr, "confirmar:"))
    tx = db.query(m.Transaccion).filter_by(borrador_id=bid).one()
    assert tx.metodo_pago == "billetera_digital" and tx.fue_corregida is True


def test_pedido_por_whatsapp_elige_fecha_y_muestra_chequeo(client_db, db):
    r = _wa(client_db, texto="pedí 2400 a andina para el 30")
    assert "¿Lo pagas el 30 de noviembre o el 30 de diciembre?" in r["respuesta_texto"]
    opcion = _boton(r, "opcion:")
    assert opcion.endswith("fecha_vencimiento=2026-11-30")
    elegido = _wa(client_db, tipo="boton", texto=opcion)
    assert "lo pagas el 30/11" in elegido["respuesta_texto"] and "⚠ Ojo" in elegido["respuesta_texto"]
    assert "Pedir S/ 1 800" in elegido["respuesta_texto"]
    final = _wa(client_db, tipo="boton", texto=_boton(elegido, "confirmar:"))
    assert "⚠ Ojo" in final["respuesta_texto"]
    bid = opcion.split(":")[1]
    deuda = db.query(m.Deuda).filter_by(borrador_id=bid).one()
    assert deuda.fecha_vencimiento.isoformat() == "2026-11-30" and deuda.proveedor_id == "PRV-0001"


def test_pregunta_va_al_asistente(client_db, db):
    r = _wa(client_db, texto="¿cómo va mi caja?")
    assert "caja del negocio" in r["respuesta_texto"] and r["botones"] == []
    assert db.query(m.Conversacion).filter_by(canal="whatsapp").count() == 2


def test_gasto_de_la_casa_explica_alcance(client_db):
    r = _wa(client_db, texto="pagué el colegio de mi hijo")
    assert "solo llevo la plata del negocio" in r["respuesta_texto"] and r["botones"] == []


def test_monto_faltante_y_respuesta_con_numero(client_db, db):
    r = _wa(client_db, texto="vendí un chupetín")
    assert "¿De cuánto fue?" in r["respuesta_texto"]
    corr = _wa(client_db, texto="1.50")
    assert "S/ 1.50" in corr["respuesta_texto"]
    _wa(client_db, tipo="boton", texto=_boton(corr, "confirmar:"))
    assert db.query(m.Transaccion).filter_by(descripcion="Vendí un chupetín").one().monto == 1.5


def test_audio_transcribe(client_db, whisper_falso):
    r = _wa(client_db, tipo="audio", texto="vendí dos cervezas", media_url="demo://audios/vendi_dos_cervezas.ogg")
    assert r["respuesta_texto"].startswith("🎙️ «vendí dos cervezas»")


def test_imagen_lee_cuaderno(client_db):
    r = _wa(client_db, tipo="imagen", media_url="demo://fotos/cuaderno_01.jpg")
    assert r["respuesta_texto"].startswith("Leí 3 fiados:") and "Sra. Carmen: S/ 120 (27/10)" in r["respuesta_texto"]
    assert [b["texto"] for b in r["botones"]] == ["Sí, guardar", "No, descartar"]


def test_descartar(client_db, db):
    r = _wa(client_db, texto="vendí un chupetín")
    bid = _boton(r, "descartar:").split(":")[1]
    assert _wa(client_db, tipo="boton", texto=f"descartar:{bid}")["respuesta_texto"] == "Listo, no lo anoté."
    assert db.get(m.Borrador, bid).estado == "descartado"


def test_enruta_por_telefono_hash(client_db):
    body = {"telefono_hash": HASH_PEDRO[:12], "tipo": "texto", "texto": "vendí dos cervezas"}
    r = client_db.post(f"{P}/webhooks/whatsapp", json=body)
    assert r.status_code == 200 and r.json()["botones"]
    desconocido = client_db.post(f"{P}/webhooks/whatsapp", json={**body, "telefono_hash": "ffffffffffff"})
    assert desconocido.status_code == 404


def test_reenvio_del_mismo_mensaje_es_idempotente(client_db, db):
    a = _wa(client_db, texto="vendí dos cervezas", mensaje_id="wamid.123")
    b = _wa(client_db, texto="vendí dos cervezas", mensaje_id="wamid.123")
    assert a == b
    assert db.query(m.Borrador).filter_by(texto_original="vendí dos cervezas").count() == 1


def test_boton_de_otro_borrador(client_db):
    assert "ya no está" in _wa(client_db, tipo="boton", texto="confirmar:BOR-9999")["respuesta_texto"]

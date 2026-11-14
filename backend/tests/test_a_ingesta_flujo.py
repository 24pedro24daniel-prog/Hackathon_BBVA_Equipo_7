"""A3–A6, A9, A11 — /ingesta/interpretar → /ingesta/confirmar (texto, voz, pedido a crédito, cuaderno) e impuestos."""

from decimal import Decimal

import pytest

from app.core.config import settings
from app.db import models as m
from app.services import alertas as motor_alertas
from app.services.ingesta import transcriptor

pytestmark = pytest.mark.db
P = settings.API_PREFIX
EMP = f"{P}/empresas/EMP-0001"


def _interpretar(cliente, texto, canal="texto", **extra):
    return cliente.post(f"{P}/ingesta/interpretar", json={"empresa_id": "EMP-0001", "canal": canal, "texto": texto,
                                                          **extra})  # fmt: skip


def _confirmar(cliente, borrador_id, **kw):
    headers = kw.pop("headers", None)
    return cliente.post(f"{P}/ingesta/confirmar", json={"borrador_id": borrador_id, **kw}, headers=headers)


# ── interpretar ──


def test_interpretar_texto_crea_borrador(client_db, db):
    r = _interpretar(client_db, "vendí dos cervezas")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["movimiento_propuesto"]["monto"] == 13.0 and d["origen_monto"] == "catalogo"
    assert d["movimiento_propuesto"]["items"][0]["producto_id"] == "PRD-0031"
    assert d["transcripcion"] is None and d["meta"]["fallback_usado"] is True
    assert d["meta"]["prompt_version"] == "extractor-v3"
    bor = db.get(m.Borrador, d["borrador_id"])
    assert bor.estado == "pendiente" and bor.texto_original == "vendí dos cervezas" and bor.fallback_usado is True
    assert bor.payload_propuesto["monto"] == 13.0 and bor.confianza == Decimal("0.920")


def test_interpretar_no_interpretable_422(client_db):
    r = _interpretar(client_db, "hola")
    assert r.status_code == 422 and r.json()["error"]["codigo"] == "NO_INTERPRETABLE"


def test_pague_el_colegio_responde_alcance_422(client_db):
    r = _interpretar(client_db, "pagué el colegio de mi hijo")
    assert r.status_code == 422
    err = r.json()["error"]
    assert "solo lleva la plata del negocio" in err["mensaje"] and err["detalles"][0]["campo"] == "alcance"


def test_sin_texto_ni_media_400(client_db):
    assert client_db.post(f"{P}/ingesta/interpretar", json={"empresa_id": "EMP-0001", "canal": "texto"}).status_code == 400


def test_empresa_inexistente_404(client_db):
    r = client_db.post(f"{P}/ingesta/interpretar", json={"empresa_id": "EMP-9999", "canal": "texto", "texto": "vendí"})
    assert r.status_code == 404


# ── voz (A4) ──


def test_voz_transcribe_con_whisper(client_db, whisper_falso, tmp_path, monkeypatch):
    audio = tmp_path / "audios" / "demo_001.ogg"
    audio.parent.mkdir()
    audio.write_bytes(b"OggS-falso")
    monkeypatch.setattr(settings, "MEDIA_DIR", str(tmp_path))
    monkeypatch.setattr(transcriptor, "BACKEND_DIR", tmp_path)
    whisper_falso.texto = "saqué 50 para la casa"
    r = _interpretar(client_db, None, canal="voz", media_url="file://audios/demo_001.ogg")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["transcripcion"] == "saqué 50 para la casa" and d["movimiento_propuesto"]["tipo"] == "retiro_personal"
    assert d["meta"]["modelo"].startswith("whisper-small + ") and whisper_falso.archivos == [str(audio.resolve())]


def test_voz_demo_sin_archivo_usa_texto_del_cliente(client_db, whisper_falso):
    r = _interpretar(client_db, "vendí dos cervezas", canal="voz", media_url="demo://audios/vendi_dos_cervezas.ogg")
    assert r.status_code == 200
    assert r.json()["transcripcion"] == "vendí dos cervezas" and whisper_falso.cargas == 0


def test_voz_sin_audio_ni_texto_422(client_db, whisper_falso):
    r = _interpretar(client_db, None, canal="voz", media_url="file://data/audios/no_existe.ogg")
    assert r.status_code == 422


def test_voz_whisper_caido_sin_texto_503(client_db, monkeypatch):
    def _caido(_url):
        raise transcriptor.TranscriptorNoDisponible("sin modelo")

    monkeypatch.setattr(transcriptor, "transcribir_media", _caido)
    r = _interpretar(client_db, None, canal="voz", media_url="file://data/audios/x.ogg")
    assert r.status_code == 503 and r.json()["error"]["codigo"] == "SERVICIO_NO_DISPONIBLE"
    r = _interpretar(client_db, "vendí dos cervezas", canal="voz", media_url="file://data/audios/x.ogg")
    assert r.status_code == 200 and r.json()["meta"]["fallback_usado"] is True


def test_media_url_no_sale_de_media_dir():
    assert transcriptor.resolver_media("file:///etc/passwd") is None
    assert transcriptor.resolver_media("file://../../etc/passwd") is None
    assert transcriptor.resolver_media("https://ejemplo.com/a.ogg") is None


# ── confirmar (A5) ──


def test_confirmar_201_registra_y_409_si_repite(client_db, db):
    bid = _interpretar(client_db, "vendí dos cervezas").json()["borrador_id"]
    r = _confirmar(client_db, bid, confirmado=True, correcciones={})
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["registros_creados"] == [{"tabla": "transacciones", "id": d["movimiento_id"]}]
    assert isinstance(d["saldo_caja_negocio"], float) and d["alertas_disparadas"] == []
    tx = db.get(m.Transaccion, d["movimiento_id"])
    assert (tx.borrador_id, tx.canal, tx.monto, tx.fue_corregida) == (bid, "texto", Decimal("13.00"), False)
    assert db.get(m.Borrador, bid).estado == "confirmado"
    assert _confirmar(client_db, bid).status_code == 409


def test_confirmar_con_correcciones(client_db, db):
    bid = _interpretar(client_db, "vendí dos cervezas").json()["borrador_id"]
    r = _confirmar(client_db, bid, correcciones={"metodo_pago": "billetera_digital", "monto": 15})
    assert r.status_code == 201
    tx = db.get(m.Transaccion, r.json()["movimiento_id"])
    assert (tx.metodo_pago, tx.monto, tx.fue_corregida) == ("billetera_digital", Decimal("15.00"), True)
    assert db.get(m.Borrador, bid).correcciones == {"metodo_pago": "billetera_digital", "monto": 15}
    det = db.query(m.DetalleTransaccion).filter_by(transaccion_id=tx.transaccion_id).one()
    assert det.subtotal == Decimal("15.00")


def test_corregir_a_retiro_para_la_casa(client_db, db):
    bid = _interpretar(client_db, "vendí dos cervezas").json()["borrador_id"]
    tx = db.get(m.Transaccion, _confirmar(client_db, bid, correcciones={"tipo": "retiro_personal"}).json()["movimiento_id"])
    assert tx.tipo == "retiro_personal" and tx.categoria_id == "CAT-15"
    assert db.query(m.DetalleTransaccion).filter_by(transaccion_id=tx.transaccion_id).count() == 0


def test_confirmar_false_descarta_204(client_db, db):
    bid = _interpretar(client_db, "saqué 50 para la casa").json()["borrador_id"]
    r = _confirmar(client_db, bid, confirmado=False)
    assert r.status_code == 204 and r.content == b""
    assert db.get(m.Borrador, bid).estado == "descartado"
    assert _confirmar(client_db, bid).status_code == 409


def test_confirmar_inexistente_404_y_correccion_invalida_400(client_db):
    assert _confirmar(client_db, "BOR-0000").status_code == 404
    bid = _interpretar(client_db, "vendí dos cervezas").json()["borrador_id"]
    assert _confirmar(client_db, bid, correcciones={"color": "rojo"}).status_code == 400
    assert _confirmar(client_db, bid, correcciones={"monto": -5}).status_code == 400
    assert _confirmar(client_db, bid).status_code == 201  # el borrador sigue pendiente tras los 400


def test_confirmar_monto_faltante_400_hasta_corregir(client_db):
    bid = _interpretar(client_db, "vendí un chupetín").json()["borrador_id"]
    r = _confirmar(client_db, bid)
    assert r.status_code == 400 and "monto" in r.json()["error"]["mensaje"]
    assert _confirmar(client_db, bid, correcciones={"monto": 1.5}).status_code == 201


def test_idempotency_key_misma_respuesta_y_conflicto(client_db, db):
    bid = _interpretar(client_db, "saqué 100 para la casa").json()["borrador_id"]
    h = {"Idempotency-Key": "wa-reenvio-1"}
    a = _confirmar(client_db, bid, headers=h)
    b = _confirmar(client_db, bid, headers=h)
    assert a.status_code == b.status_code == 201 and a.json() == b.json()
    assert db.query(m.Transaccion).filter_by(borrador_id=bid).count() == 1
    otro = _interpretar(client_db, "saqué 10 para la casa").json()["borrador_id"]
    assert _confirmar(client_db, otro, headers=h).status_code == 409


def test_gasto_de_la_casa_con_monto(client_db, db):
    d = _interpretar(client_db, "pagué el colegio, 150").json()
    assert d["fuera_de_alcance"] is True and d["campos_faltantes"] == ["salio_de_caja"]
    assert [o["valor"] for o in d["opciones_aclaracion"]] == ["si", "no"]
    assert _confirmar(client_db, d["borrador_id"], correcciones={"salio_de_caja": "no"}).status_code == 204
    d2 = _interpretar(client_db, "pagué el colegio, 150").json()
    r = _confirmar(client_db, d2["borrador_id"], correcciones={"salio_de_caja": "si"})
    assert r.status_code == 201 and db.get(m.Transaccion, r.json()["movimiento_id"]).tipo == "retiro_personal"


# ── pedido a crédito (A6) ──


def test_pedido_a_credito_pregunta_fecha_y_trae_chequeo(client_db):
    d = _interpretar(client_db, "pedí 2 400 a Andina para el 30").json()
    mov = d["movimiento_propuesto"]
    assert (mov["tipo"], mov["metodo_pago"], mov["monto"], mov["contraparte"]) == (
        "compra", "credito", 2400.0, "Distribuidora Andina")
    assert d["campos_faltantes"] == ["fecha_vencimiento"]
    assert d["pregunta_aclaratoria"] == "¿Lo pagas el 30 de noviembre o el 30 de diciembre?"
    assert d["opciones_aclaracion"][0] == {"valor": "2026-11-30", "texto": "30/11"}
    ch = d["chequeo_pedido"]
    assert ch["estado_caja"] == "no_te_alcanza" and ch["fecha_vencimiento"] == "2026-11-30"
    assert {"saldo_proyectado_al_vencimiento", "sugerencias", "fundamento", "limites", "confianza"} <= set(ch)


def test_confirmar_pedido_crea_deuda_y_dispara_alertas(client_db, db, monkeypatch):
    llamadas = []
    original = motor_alertas.evaluar_alertas

    def _espia(db_, empresa_id, disparador=None, entidad_id=None):
        llamadas.append((disparador, entidad_id))
        return original(db_, empresa_id, disparador, entidad_id)

    monkeypatch.setattr(motor_alertas, "evaluar_alertas", _espia)
    bid = _interpretar(client_db, "pedí 2 400 a Andina para el 30").json()["borrador_id"]
    r = _confirmar(client_db, bid, correcciones={"fecha_vencimiento": "2026-11-30"})
    assert r.status_code == 201, r.text
    d = r.json()
    assert [x["tabla"] for x in d["registros_creados"]] == ["transacciones", "deudas"]
    deuda_id = d["registros_creados"][1]["id"]
    assert llamadas == [("compra_credito", deuda_id)]
    assert d["alertas_disparadas"][0]["tipo"] == "faltante_caja"
    assert d["chequeo_pedido"]["fecha_vencimiento"] == "2026-11-30"
    tx = db.get(m.Transaccion, d["movimiento_id"])
    assert tx.afecta_caja is False and db.get(m.Deuda, deuda_id).fecha_vencimiento.isoformat() == "2026-11-30"


def test_alertas_que_fallan_no_tumban_el_registro(client_db, monkeypatch):
    def _roto(*_a, **_k):
        raise RuntimeError("motor caído")

    monkeypatch.setattr(motor_alertas, "evaluar_alertas", _roto)
    bid = _interpretar(client_db, "saqué 50 para la casa").json()["borrador_id"]
    r = _confirmar(client_db, bid)
    assert r.status_code == 201 and r.json()["alertas_disparadas"] == []


# ── cuaderno (A11) ──


def test_cuaderno_fixture_y_confirmar_sin_duplicar(client_db, db):
    r = client_db.post(f"{P}/ingesta/cuaderno", json={"empresa_id": "EMP-0001",
                                                      "media_url": "demo://fotos/cuaderno_01.jpg"})  # fmt: skip
    assert r.status_code == 200
    d = r.json()
    assert len(d["fiados_propuestos"]) == 3 and d["meta"]["fallback_usado"] is True and d["lineas_no_legibles"] == 1
    assert db.get(m.Borrador, d["borrador_id"]).canal == "foto"
    fiados = [{**f} for f in d["fiados_propuestos"]]
    fiados[1]["monto"] = 35  # Pedro corrige el monto de Don Luis
    c = _confirmar(client_db, d["borrador_id"], correcciones={"fiados": fiados})
    assert c.status_code == 201, c.text
    cuerpo = c.json()
    assert len(cuerpo["duplicados"]) == 2  # Carmen 120 y Rosa 95 ya estaban
    assert [x["tabla"] for x in cuerpo["registros_creados"]] == ["transacciones", "cuaderno_fiado"]
    nuevo = db.get(m.CuadernoFiado, cuerpo["registros_creados"][1]["id"])
    assert (nuevo.cliente_id, nuevo.monto, nuevo.canal, nuevo.fecha_fiado.isoformat()) == (
        "CLI-0087", Decimal("35.00"), "foto", "2026-11-02")


def test_cuaderno_con_cliente_nuevo(client_db, db):
    d = client_db.post(f"{P}/ingesta/cuaderno", json={"empresa_id": "EMP-0001",
                                                      "media_url": "file://data/fotos/cuaderno_02.jpg"}).json()  # fmt: skip
    c = _confirmar(client_db, d["borrador_id"]).json()
    tablas = [x["tabla"] for x in c["registros_creados"]]
    assert tablas.count("cuaderno_fiado") == 2 and "clientes" in tablas


def test_cuaderno_foto_desconocida_vacia(client_db):
    d = client_db.post(f"{P}/ingesta/cuaderno", json={"empresa_id": "EMP-0001", "media_url": "demo://fotos/x.jpg"}).json()
    assert d["fiados_propuestos"] == [] and d["meta"]["fallback_usado"] is True


# ── impuestos (A9) ──


def test_impuesto_pagado_registra_transaccion(client_db, db):
    r = client_db.post(f"{EMP}/impuestos", json={"periodo": "2026-11", "regimen": "nuevo_rus", "pagado": True,
                                                 "monto": 20, "fecha_pago": "2026-11-14"})  # fmt: skip
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["impuesto_id"] == "IMP-0004" and d["estado"] == "al_dia" and d["ya_registrado"] is False
    assert d["proximo_vencimiento"] == "2027-01-15"
    tx = db.get(m.Transaccion, d["movimiento_id"])
    assert (tx.tipo, tx.impuesto_id, tx.monto) == ("pago_impuesto", "IMP-0004", Decimal("20.00"))
    otra = client_db.post(f"{EMP}/impuestos", json={"periodo": "2026-11", "pagado": True, "monto": 20}).json()
    assert otra["ya_registrado"] is True and db.query(m.Transaccion).filter_by(impuesto_id="IMP-0004").count() == 1


def test_impuesto_no_pagado_queda_pendiente(client_db):
    d = client_db.post(f"{EMP}/impuestos", json={"periodo": "2026-12", "pagado": False, "monto": 20}).json()
    assert d["estado"] == "pendiente" and d["proximo_vencimiento"] == "2026-12-15"

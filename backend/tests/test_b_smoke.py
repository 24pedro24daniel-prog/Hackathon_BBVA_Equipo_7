"""Smoke tests de la Fase 0 (Dev B): todos los endpoints responden con el JSON del contrato.

Ejecutar desde backend/:  pytest tests/test_b_smoke.py -v
No requieren BD (los stubs no la usan).
"""
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings, settings
from app.main import app
from app.mocks import data as mock

E = "/api/v1/empresas/EMP-0001"


@pytest.fixture(autouse=True)
def _estado_limpio():
    mock.ESTADO["saldo"] = 2340.0
    mock.BORRADORES.clear()
    yield
    mock.ESTADO["saldo"] = 2340.0


@pytest.fixture
def client():
    return TestClient(app, headers={"X-API-Key": settings.API_KEY.get_secret_value()})


# ---------- público / auth / errores ----------
def test_health_publico():
    r = TestClient(app).get("/api/v1/health")
    assert r.status_code == 200
    assert r.json()["version_api"] == "1.0.0"
    assert "componentes" in r.json()


def test_sin_api_key_401():
    r = TestClient(app).get(f"{E}/resumen")
    assert r.status_code == 401
    assert r.json()["error"]["codigo"] == "NO_AUTORIZADO"
    assert r.json()["error"]["request_id"].startswith("req_")


def test_validacion_400_formato_contrato(client):
    r = client.post(f"{E}/pedidos/chequeo", json={"proveedor": "Andina"})
    assert r.status_code == 400
    err = r.json()["error"]
    assert err["codigo"] == "VALIDACION" and err["detalles"] and err["request_id"]


def test_ruta_inexistente_404_formato_contrato(client):
    r = client.get("/api/v1/no-existe")
    assert r.status_code == 404
    assert r.json()["error"]["codigo"] == "NO_ENCONTRADO"


# ---------- B: lecturas ----------
def test_resumen_dinero_es_numero(client):
    r = client.get(f"{E}/resumen?periodo=2026-11")
    assert r.status_code == 200
    saldo = r.json()["indicadores"]["saldo_caja_negocio"]["valor"]
    assert isinstance(saldo, float) and saldo == 2340.0


def test_forecast_dia_critico(client):
    r = client.get(f"{E}/forecast?horizonte_dias=30")
    assert r.status_code == 200
    j = r.json()
    assert len(j["serie"]) == 30
    assert j["dia_critico"]["fecha"] == "2026-11-30"
    assert j["dia_critico"]["saldo_p50"] == -650.0
    assert j["meta"]["request_id"].startswith("req_")


def test_fiados_y_recordatorio(client):
    j = client.get(f"{E}/fiados").json()
    assert j["total_pendiente"] == 310.0 and len(j["items"]) == 3
    r = client.post("/api/v1/fiados/FIA-0045/recordatorio")
    assert "Sra. Carmen" in r.json()["mensaje"] and "S/ 120 " in r.json()["mensaje"]
    assert client.post("/api/v1/fiados/FIA-9999/recordatorio").status_code == 404


def test_pedidos(client):
    j = client.get(f"{E}/pedidos").json()
    assert j["total_pendiente"] == 2400.0
    assert j["items"][0]["pedido_id"] == "PED-0012"
    assert j["impuestos"]["estado"] == "al_dia"


def test_analisis_y_alertas(client):
    assert client.get(f"{E}/analisis?agrupar_por=metodo_pago").status_code == 200
    j = client.get(f"{E}/alertas").json()
    assert j["items"][0]["tipo"] == "faltante_caja" and len(j["items"][0]["causas"]) == 3


# ---------- B: cálculos del mock (coinciden con contract.md) ----------
def test_chequeo_2400(client):
    j = client.post(f"{E}/pedidos/chequeo",
                    json={"proveedor": "Distribuidora Andina", "monto": 2400, "fecha_vencimiento": "2026-11-30"}).json()
    assert j["saldo_proyectado_al_vencimiento"] == -650.0
    assert j["estado_caja"] == "no_te_alcanza"
    assert [s["saldo_resultante"] for s in j["sugerencias"]] == [-50.0, 550.0, 850.0]


def test_simular_combinado(client):
    body = {"acciones": [{"tipo": "reducir_pedido", "pedido_id": "PED-0012", "nuevo_monto": 1800},
                         {"tipo": "pagar_en_partes", "pedido_id": "PED-0012", "partes": 2}]}
    j = client.post(f"{E}/simular", json=body).json()
    assert j["sin_acciones"]["saldo_minimo"] == -650.0
    assert j["con_acciones"]["saldo_minimo"] == 850.0
    assert j["con_acciones"]["estado_caja"] == "te_alcanza"
    assert j["mejora"] == 1500.0


def test_ajuste_y_preferencias(client):
    r = client.post(f"{E}/forecast/ajustes", json={"fecha": "2026-11-28", "concepto": "alquiler", "monto": 0, "motivo": "acuerdo"})
    assert r.status_code == 201 and r.json()["forecast_recalculado"] is True
    r = client.put(f"{E}/preferencias-alertas", json={"canales": ["whatsapp"], "max_por_dia": 2})
    assert r.status_code == 200 and r.json()["silencio_desde"] == "21:00"
    r = client.post("/api/v1/alertas/ALR-0007/accion", json={"accion": "descartada"})
    assert r.json()["estado"] == "descartada"


# ---------- Cruce A → B (PLAN §4.3) ----------
def test_flujo_venta_cambia_saldo(client):
    b = client.post("/api/v1/ingesta/interpretar", json={"empresa_id": "EMP-0001", "canal": "texto", "texto": "vendí dos cervezas"}).json()
    assert b["movimiento_propuesto"]["monto"] == 13.0
    c = client.post("/api/v1/ingesta/confirmar", json={"borrador_id": b["borrador_id"], "confirmado": True})
    assert c.status_code == 201
    assert c.json()["saldo_caja_negocio"] == 2353.0
    assert c.json()["alertas_disparadas"] == []


def test_flujo_pedido_credito_dispara_alerta(client):
    b = client.post("/api/v1/ingesta/interpretar", json={"canal": "texto", "texto": "pedí 2 400 a Andina para pagar el 30"}).json()
    assert b["movimiento_propuesto"]["monto"] == 2400.0 and b["campos_faltantes"] == ["fecha_vencimiento"]
    c = client.post("/api/v1/ingesta/confirmar", json={"borrador_id": b["borrador_id"], "confirmado": True}).json()
    assert [a["tipo"] for a in c["alertas_disparadas"]] == ["faltante_caja"]


def test_confirmar_descartar_204_y_borrador_inexistente_404(client):
    b = client.post("/api/v1/ingesta/interpretar", json={"canal": "texto", "texto": "saqué 50 para la casa"}).json()
    assert client.post("/api/v1/ingesta/confirmar", json={"borrador_id": b["borrador_id"], "confirmado": False}).status_code == 204
    assert client.post("/api/v1/ingesta/confirmar", json={"borrador_id": "BOR-0", "confirmado": True}).status_code == 404


def test_no_interpretable_422(client):
    r = client.post("/api/v1/ingesta/interpretar", json={"canal": "texto", "texto": "hola qué tal"})
    assert r.status_code == 422 and r.json()["error"]["codigo"] == "NO_INTERPRETABLE"


def test_asistente_y_salud_stub(client):
    r = client.post(f"{E}/asistente/mensajes", json={"mensaje": "¿cómo va mi caja?"})
    assert r.json()["intencion"] == "estado_caja"
    assert client.get(f"{E}/salud").json()["score"] == 71


# ---------- core ----------
def test_reloj_usa_fecha_demo(monkeypatch):
    from app.core import reloj
    monkeypatch.setenv("FECHA_DEMO", "2026-11-14")
    get_settings.cache_clear()
    try:
        assert reloj.hoy() == date(2026, 11, 14)
        assert reloj.ahora().date() == date(2026, 11, 14)
        assert reloj.ahora().tzinfo is not None
    finally:
        get_settings.cache_clear()


def test_cursor_roundtrip():
    from app.core.paginacion import codificar_cursor, decodificar_cursor, recortar
    assert decodificar_cursor(codificar_cursor({"id": "MOV-000123", "t": "2026-11-14"})) == {"id": "MOV-000123", "t": "2026-11-14"}
    items, nxt = recortar([1, 2, 3], 2, lambda x: {"i": x})
    assert items == [1, 2] and decodificar_cursor(nxt) == {"i": 2}
    assert recortar([1, 2], 2, lambda x: {"i": x}) == ([1, 2], None)

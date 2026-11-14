"""Formato de error del contrato (§0) y autenticación X-API-Key."""

import re

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.core.config import settings
from app.core.errors import Conflicto, registrar_handlers
from app.main import RequestIdMiddleware, app

PREFIJO = settings.API_PREFIX
EMP = f"{PREFIJO}/empresas/EMP-0001"


def _es_error_contrato(cuerpo: dict, codigo: str) -> None:
    assert set(cuerpo) == {"error"}
    err = cuerpo["error"]
    assert set(err) == {"codigo", "mensaje", "detalles", "request_id"}
    assert err["codigo"] == codigo
    assert isinstance(err["mensaje"], str) and err["mensaje"]
    assert isinstance(err["detalles"], list)
    assert re.fullmatch(r"req_[0-9a-f]{6}", err["request_id"])


# ── formato de error ──


def test_validacion_400_con_detalles_campo_problema(client):
    r = client.post(f"{EMP}/pedidos/chequeo", json={"proveedor": "Distribuidora Andina", "fecha_vencimiento": "2026-11-30"})
    assert r.status_code == 400
    _es_error_contrato(r.json(), "VALIDACION")
    detalle = r.json()["error"]["detalles"][0]
    assert detalle["campo"] == "monto" and detalle["problema"]


def test_validacion_de_query(client):
    r = client.get(f"{EMP}/forecast", params={"horizonte_dias": 0})
    assert r.status_code == 400
    _es_error_contrato(r.json(), "VALIDACION")
    assert r.json()["error"]["detalles"][0]["campo"] == "horizonte_dias"


def test_ruta_inexistente_404(client):
    r = client.get(f"{PREFIJO}/no-existe")
    assert r.status_code == 404
    _es_error_contrato(r.json(), "NO_ENCONTRADO")


def test_request_id_coincide_con_header(client):
    r = client.get(f"{PREFIJO}/no-existe")
    assert r.headers["x-request-id"] == r.json()["error"]["request_id"]


def test_request_id_entrante_se_respeta(client):
    r = client.get(f"{EMP}/forecast", headers={"X-Request-ID": "req_abc123"})
    assert r.headers["x-request-id"] == "req_abc123"
    assert r.json()["meta"]["request_id"] == "req_abc123"


def test_errores_de_dominio_y_500_con_formato_del_contrato():
    mini = FastAPI()
    mini.add_middleware(RequestIdMiddleware)
    registrar_handlers(mini)

    @mini.get("/conflicto")
    def _conflicto():
        raise Conflicto("Ese registro ya fue confirmado.", [{"campo": "borrador_id", "problema": "confirmado"}])

    @mini.get("/explota")
    def _explota():
        raise RuntimeError("detalle interno que no debe filtrarse")

    c = TestClient(mini, raise_server_exceptions=False)
    r = c.get("/conflicto")
    assert r.status_code == 409
    _es_error_contrato(r.json(), "CONFLICTO")
    r = c.get("/explota")
    assert r.status_code == 500
    _es_error_contrato(r.json(), "ERROR_INTERNO")
    assert "detalle interno" not in r.text


# ── X-API-Key ──


def test_sin_api_key_401(client_sin_key):
    r = client_sin_key.get(f"{EMP}/resumen")
    assert r.status_code == 401
    _es_error_contrato(r.json(), "NO_AUTORIZADO")


def test_api_key_invalida_401(client_sin_key):
    r = client_sin_key.get(f"{EMP}/resumen", headers={"X-API-Key": "otra-clave"})
    assert r.status_code == 401
    _es_error_contrato(r.json(), "NO_AUTORIZADO")


def test_api_key_valida_200(client):
    assert client.get(f"{EMP}/resumen").status_code == 200


def test_servidor_sin_api_key_configurada_rechaza_todo(client, monkeypatch):
    monkeypatch.setattr(settings, "API_KEY", SecretStr(""))
    r = client.get(f"{EMP}/resumen", headers={"X-API-Key": ""})
    assert r.status_code == 401
    r = client.get(f"{EMP}/resumen", headers={"X-API-Key": "cualquiera"})
    assert r.status_code == 401


def test_health_es_publico(client_sin_key):
    assert client_sin_key.get(f"{PREFIJO}/health").status_code == 200


_VALORES_PATH = {"{empresa_id}": "EMP-0001", "{fiado_id}": "FIA-0045", "{alerta_id}": "ALR-0007"}


def _rutas_protegidas():
    """Rutas desde el esquema OpenAPI (FastAPI anida los routers incluidos)."""
    for path, operaciones in app.openapi()["paths"].items():
        if path.endswith("/health"):
            continue
        for marcador, valor in _VALORES_PATH.items():
            path = path.replace(marcador, valor)
        for metodo in sorted(operaciones):
            yield metodo.upper(), path


@pytest.mark.parametrize(("metodo", "path"), list(_rutas_protegidas()))
def test_todas_las_rutas_exigen_api_key(client_sin_key, metodo, path):
    r = client_sin_key.request(metodo, path)
    assert r.status_code == 401, f"{metodo} {path} respondió {r.status_code} sin X-API-Key"
    assert r.json()["error"]["codigo"] == "NO_AUTORIZADO"


def test_hay_rutas_protegidas_registradas():
    assert len(list(_rutas_protegidas())) == 23  # + /health pública = 24 endpoints

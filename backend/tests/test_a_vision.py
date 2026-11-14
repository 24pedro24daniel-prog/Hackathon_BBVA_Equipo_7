"""A11 — Foto del cuaderno con un VLM vía OpenRouter (mockeado: ningún test llama a la red) + fallback a fixture."""

import hashlib
import json
from datetime import date

import httpx
import pytest
from pydantic import SecretStr

from app.core.config import settings
from app.services.ingesta import vision

pytestmark = pytest.mark.db
P = settings.API_PREFIX
EMP = "EMP-0001"
JPEG = b"\xff\xd8\xff\xe0" + b"0" * 64
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64
CLAVE_FOTO = f"empresas/{EMP}/fotos/2026/11/9a1c0000-0000-4000-8000-000000000001.jpg"


def _respuesta(fiados, no_legibles=0, *, argumentos=None):
    args = argumentos if argumentos is not None else json.dumps({"fiados": fiados, "lineas_no_legibles": no_legibles})
    llamada = {"id": "c1", "type": "function", "function": {"name": "registrar_fiados", "arguments": args}}
    return {"choices": [{"message": {"role": "assistant", "content": None, "tool_calls": [llamada]}}]}


def _f(cliente, monto, fecha="2026-11-10", concepto=None, tachado=False, legible=True):
    return {"cliente": cliente, "monto": monto, "fecha": fecha, "concepto": concepto, "tachado": tachado,
            "legible": legible}  # fmt: skip


@pytest.fixture
def media(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "MEDIA_DIR", str(tmp_path))
    (tmp_path / "fotos").mkdir()

    def poner(nombre="cuaderno_nuevo.jpg", datos=JPEG):
        (tmp_path / "fotos" / nombre).write_bytes(datos)
        return f"demo://fotos/{nombre}"

    return poner


def _cuaderno(cliente, url):
    return cliente.post(f"{P}/ingesta/cuaderno", json={"empresa_id": EMP, "media_url": url})


# ── lectura con VLM ──


def test_vlm_tres_fiados_alias_nuevo_y_tachado(client_db, llm_falso, media):
    llm_falso.respuesta = _respuesta([
        _f("Rosa", 12.5, "2026-11-12", "pan, huevos"),
        _f("Marcos", "S/ 8.00", "2026-11-13"),
        _f("Don Luis", 35, "2026-11-02", tachado=True),
    ], no_legibles=1)
    r = _cuaderno(client_db, media())
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["meta"]["fallback_usado"] is False and d["meta"]["modelo"] == "vlm-openrouter"
    assert d["meta"]["modelo_version"] == settings.VLM_MODEL and d["meta"]["prompt_version"] == "cuaderno-v2"
    assert d["lineas_no_legibles"] == 1 and d["lineas_tachadas"] == 1
    rosa, marcos = d["fiados_propuestos"]
    assert (rosa["cliente"], rosa["cliente_id"], rosa["cliente_nuevo"], rosa["monto"]) == (
        "Vecina Rosa", "CLI-0110", False, 12.5)
    assert (marcos["cliente"], marcos["cliente_id"], marcos["cliente_nuevo"], marcos["monto"]) == (
        "Marcos", None, True, 8.0)
    assert rosa["detalle"] == "pan, huevos" and 0 < rosa["confianza"] <= 1


def test_vlm_payload_data_url_y_modelo(client_db, llm_falso, media, monkeypatch):
    monkeypatch.setattr(settings, "VLM_MODEL", "google/gemini-2.0-flash-001")
    llm_falso.respuesta = _respuesta([_f("Rosa", 10)])
    assert _cuaderno(client_db, media(datos=PNG)).status_code == 200
    (llamada,) = llm_falso.llamadas
    payload = llamada["payload"]
    assert payload["model"] == "google/gemini-2.0-flash-001"
    assert payload["tool_choice"]["function"]["name"] == "registrar_fiados"
    partes = payload["messages"][1]["content"]
    url = next(p["image_url"]["url"] for p in partes if p["type"] == "image_url")
    assert url.startswith("data:image/png;base64,") and "r2://" not in json.dumps(payload)
    assert llamada["timeout"].read == settings.VLM_TIMEOUT_S
    assert "Authorization" in llamada["headers"]


def test_vlm_fechas_relativas_y_sin_anio():
    hoy = date(2026, 11, 14)  # sábado
    assert vision._fecha("12/11", hoy) == date(2026, 11, 12)
    assert vision._fecha("20/12", hoy) == date(2025, 12, 20)  # futuro → año anterior
    assert vision._fecha("lunes", hoy) == date(2026, 11, 9)
    assert vision._fecha("Sábado", hoy) == hoy
    assert vision._fecha("ayer", hoy) == date(2026, 11, 13)
    assert vision._fecha("2026-12-01", hoy) == date(2025, 12, 1)
    assert vision._fecha("basura", hoy) is None and vision._fecha("31/02", hoy) is None


def test_vlm_fecha_ausente_usa_hoy_con_menos_confianza(llm_falso):
    llm_falso.respuesta = _respuesta([_f("Ana", 10, fecha="12/11"), _f("Eva", 5, fecha=None)])
    ana, eva = vision.leer(JPEG, "image/jpeg").fiados
    assert ana["fecha"] == "2026-11-12" and eva["fecha"] == "2026-11-14" and eva["confianza"] < ana["confianza"]


def test_vlm_tolera_null_y_descarta_montos_absurdos(llm_falso):
    llm_falso.respuesta = _respuesta([
        _f("Ana", 10), _f("Cero", 0), _f("Negativo", -5), _f("Enorme", 999999), _f("", 5), _f("Sin monto", None),
        _f("Ilegible", 7, legible=False),
    ], no_legibles=None)
    lectura = vision.leer(JPEG, "image/jpeg")
    assert [f["cliente"] for f in lectura.fiados] == ["Ana"] and lectura.lineas_no_legibles == 6
    llm_falso.respuesta = _respuesta(None, argumentos=json.dumps({"fiados": None, "lineas_no_legibles": None}))
    assert vision.leer(JPEG, "image/jpeg").fiados == []


@pytest.mark.parametrize("argumentos", ["{no es json", json.dumps({"fiados": "texto"}), json.dumps([1, 2])])
def test_vlm_salida_invalida_levanta(llm_falso, argumentos):
    llm_falso.respuesta = _respuesta(None, argumentos=argumentos)
    with pytest.raises(vision.SalidaInvalida):
        vision.leer(JPEG, "image/jpeg")


def test_vlm_sin_tool_call_levanta(llm_falso):
    with pytest.raises(vision.SalidaInvalida):
        vision.leer(JPEG, "image/jpeg")


# ── fallback ──


def test_json_invalido_cae_a_fixture(client_db, llm_falso, media):
    llm_falso.respuesta = _respuesta(None, argumentos="{roto")
    d = _cuaderno(client_db, media("cuaderno_01.jpg")).json()
    assert d["meta"]["fallback_usado"] is True and d["meta"]["modelo"] == "fixture-cuaderno"
    assert len(d["fiados_propuestos"]) == 3 and len(llm_falso.llamadas) == 1


@pytest.mark.parametrize("error", [
    httpx.ReadTimeout("lento"),
    httpx.HTTPStatusError("x", request=httpx.Request("POST", "http://x"), response=httpx.Response(502)),
])
def test_timeout_o_error_http_cae_a_fixture(client_db, llm_falso, media, error):
    llm_falso.error = error
    d = _cuaderno(client_db, media("cuaderno_02.jpg")).json()
    assert d["meta"]["fallback_usado"] is True and len(d["fiados_propuestos"]) == 2


def test_timeout_foto_desconocida_vacia(client_db, llm_falso, media):
    llm_falso.error = httpx.ConnectTimeout("lento")
    d = _cuaderno(client_db, media("foto_rara.jpg")).json()
    assert d["fiados_propuestos"] == [] and d["meta"]["fallback_usado"] is True


def test_sin_key_fixture_y_vacio(client_db, media):
    assert not settings.llm_configurado
    d = _cuaderno(client_db, media("cuaderno_01.jpg")).json()
    assert len(d["fiados_propuestos"]) == 3 and d["meta"]["fallback_usado"] is True
    assert _cuaderno(client_db, "demo://fotos/no_existe.jpg").json()["fiados_propuestos"] == []


def test_con_key_pero_sin_archivo_usa_fixture_sin_llamar(client_db, llm_falso):
    d = _cuaderno(client_db, "demo://fotos/cuaderno_03.jpg").json()
    assert d["meta"]["fallback_usado"] is True and len(d["fiados_propuestos"]) == 1 and llm_falso.llamadas == []


# ── validación de la imagen ──


def test_imagen_de_tipo_invalido_400(client_db, llm_falso, media):
    r = _cuaderno(client_db, media("falsa.jpg", b"%PDF-1.4 no es una imagen"))
    assert r.status_code == 400 and r.json()["error"]["detalles"][0]["campo"] == "media_url"
    assert llm_falso.llamadas == []


def test_imagen_demasiado_grande_400(client_db, llm_falso, media, monkeypatch):
    monkeypatch.setattr(settings, "MEDIA_MAX_IMAGEN_BYTES", 32)
    assert _cuaderno(client_db, media()).status_code == 400 and llm_falso.llamadas == []


# ── flujos completos ──


def test_flujo_r2_vlm_y_confirmar_con_duplicado(client_db, llm_falso, s3_falso):
    url = s3_falso.poner(CLAVE_FOTO, JPEG, "image/jpeg")
    llm_falso.respuesta = _respuesta([_f("Carmen", 120, "27/10"), _f("Pedrito", 9.5, "2026-11-13")])
    d = _cuaderno(client_db, url).json()
    assert d["meta"]["fallback_usado"] is False
    carmen, pedrito = d["fiados_propuestos"]
    assert carmen["cliente"] == "Sra. Carmen" and carmen["posible_duplicado"] is True
    assert pedrito["cliente_nuevo"] is True
    assert "r2://" not in json.dumps(llm_falso.llamadas[0]["payload"])
    c = client_db.post(f"{P}/ingesta/confirmar", json={"borrador_id": d["borrador_id"], "confirmado": True})
    assert c.status_code == 201, c.text
    assert len(c.json()["duplicados"]) == 1
    tablas = [x["tabla"] for x in c.json()["registros_creados"]]
    assert tablas.count("cuaderno_fiado") == 1 and "clientes" in tablas


def test_flujo_r2_tipo_no_imagen_400(client_db, llm_falso, s3_falso):
    url = s3_falso.poner(CLAVE_FOTO, JPEG, "audio/ogg")
    assert _cuaderno(client_db, url).status_code == 400 and llm_falso.llamadas == []


def test_webhook_imagen_con_vlm(client_db, llm_falso, media):
    llm_falso.respuesta = _respuesta([_f("Rosa", 15.5, "2026-11-12")])
    body = {"telefono_hash": hashlib.sha256(b"+51900000001").hexdigest(), "empresa_id": EMP, "tipo": "imagen",
            "media_url": media()}  # fmt: skip
    r = client_db.post(f"{P}/webhooks/whatsapp", json=body)
    assert r.status_code == 200, r.text
    texto = r.json()["respuesta_texto"]
    assert texto.startswith("Leí 1 fiados:") and "Vecina Rosa: S/ 15.5" in texto


# ── health ──


def test_health_reporta_vlm_sin_red(client, llm_falso):
    c = client.get(f"{P}/health").json()["componentes"]["vlm"]
    assert c == {"estado": "ok", "modelo": settings.VLM_MODEL, "proveedor": "openrouter"}
    assert llm_falso.llamadas == []


def test_health_vlm_sin_configurar(client, monkeypatch):
    monkeypatch.setattr(settings, "OPENROUTER_API_KEY", SecretStr(""))
    assert client.get(f"{P}/health").json()["componentes"]["vlm"]["estado"] == "sin_configurar"

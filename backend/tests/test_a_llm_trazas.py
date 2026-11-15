"""Trazabilidad del LLM/VLM: tabla llm_llamadas, instrumentación de llm_client, consumidores y endpoints.

Sin red (fixture `llm_falso`) y siempre contra la BD de pruebas (fixtures `db` / `client_db`).
"""

import base64
import hashlib
import json
from datetime import timedelta

import httpx
import pytest
from sqlalchemy import delete, select

from app.core.config import settings
from app.core.ids import nuevo_id
from app.core.reloj import ahora
from app.db import models as m
from app.services.ingesta import llm_client, traza_llm

pytestmark = pytest.mark.db
P = settings.API_PREFIX
EMP = "EMP-0001"
MSG = [{"role": "user", "content": "vendí dos cervezas"}]
JPEG = b"\xff\xd8\xff\xe0" + b"7" * 64


@pytest.fixture(autouse=True)
def _tabla_limpia(db):
    """Otros tests pueden haber dejado filas comprometidas; aquí se parte de cero (se revierte al final)."""
    db.execute(delete(m.LlmLlamada))
    db.flush()


def _ok(contenido="ok", *, tool_calls=None, modelo="openai/gpt-4o-mini-2024-07-18", gen="gen-abc123"):
    mensaje = {"role": "assistant", "content": contenido}
    if tool_calls:
        mensaje["tool_calls"] = tool_calls
    return {"id": gen, "model": modelo,
            "choices": [{"message": mensaje, "finish_reason": "tool_calls" if tool_calls else "stop"}],
            "usage": {"prompt_tokens": 120, "completion_tokens": 30, "total_tokens": 150, "cost": 0.0000306}}  # fmt: skip


def _tool(nombre, argumentos):
    return [{"id": "c1", "type": "function", "function": {"name": nombre, "arguments": json.dumps(argumentos)}}]


def _filas(db):
    return db.scalars(select(m.LlmLlamada).order_by(m.LlmLlamada.llamada_id)).all()


def _una(db):
    filas = _filas(db)
    assert len(filas) == 1
    return filas[0]


def _traza(db, origen="extractor"):
    return traza_llm.crear(db, EMP, origen, "prueba-v1")


# ── llm_client ──


def test_llamada_ok_guarda_tokens_costo_modelo_y_latencia(db, llm_falso):
    llm_falso.respuesta = _ok("hola")
    traza = _traza(db)
    llm_client.chat_completion(MSG, traza=traza, max_tokens=50)
    f = _una(db)
    assert f.llamada_id == "LLM-000001" == traza.llamada_id
    assert (f.empresa_id, f.origen, f.estado, f.http_status, f.proveedor) == (EMP, "extractor", "ok", 200, "openrouter")
    assert (f.prompt_tokens, f.completion_tokens, f.total_tokens) == (120, 30, 150)
    assert float(f.costo_usd) == pytest.approx(0.0000306)
    assert f.modelo_solicitado == settings.LLM_MODEL
    assert f.modelo_respondido == "openai/gpt-4o-mini-2024-07-18" and f.generation_id == "gen-abc123"
    assert f.latencia_ms is not None and f.latencia_ms >= 0
    assert f.prompt_version == "prueba-v1" and f.resultado_uso is None and f.error is None
    assert f.request["messages"] == MSG and f.request["max_tokens"] == 50
    assert f.respuesta == {"finish_reason": "stop", "content": "hola"}
    assert f.creado_en.date() == ahora().date()


def test_payload_pide_el_uso_a_openrouter(db, llm_falso):
    llm_client.chat_completion(MSG, traza=_traza(db))
    assert llm_falso.llamadas[0]["payload"]["usage"] == {"include": True}


def test_sin_traza_no_escribe_nada(db, llm_falso):
    llm_client.chat_completion(MSG)
    assert _filas(db) == []


def test_tool_calls_crudos_en_la_respuesta(db, llm_falso):
    llamadas = _tool("registrar_movimiento", {"tipo": "venta"})
    llm_falso.respuesta = _ok(None, tool_calls=llamadas)
    llm_client.chat_completion(MSG, traza=_traza(db), tools=[{"type": "function", "function": {"name": "x"}}],
                               tool_choice="auto")  # fmt: skip
    f = _una(db)
    assert f.respuesta["tool_calls"] == llamadas and f.respuesta["finish_reason"] == "tool_calls"
    assert f.request["tools"] == [{"type": "function", "function": {"name": "x"}}]
    assert f.request["tool_choice"] == "auto"


def test_timeout(db, llm_falso):
    llm_falso.error = httpx.ReadTimeout("lento")
    with pytest.raises(llm_client.LLMNoDisponible):
        llm_client.chat_completion(MSG, traza=_traza(db), timeout_s=7)
    f = _una(db)
    assert f.estado == "timeout" and f.http_status is None and "7" in f.error
    assert f.prompt_tokens is None and f.latencia_ms is not None


def test_http_429(db, llm_falso):
    req = httpx.Request("POST", "https://x")
    cuerpo = {"error": {"message": "Rate limit exceeded", "code": 429}}
    llm_falso.error = httpx.HTTPStatusError("429", request=req, response=httpx.Response(429, request=req, json=cuerpo))
    with pytest.raises(llm_client.LLMNoDisponible):
        llm_client.chat_completion(MSG, traza=_traza(db))
    f = _una(db)
    assert f.estado == "http_error" and f.http_status == 429
    assert "Rate limit exceeded" in f.error


def test_error_de_red(db, llm_falso):
    llm_falso.error = httpx.ConnectError("sin red")
    with pytest.raises(llm_client.LLMNoDisponible):
        llm_client.chat_completion(MSG, traza=_traza(db))
    assert _una(db).estado == "red"


def test_json_sin_choices(db, llm_falso):
    llm_falso.respuesta = {"error": {"message": "modelo no disponible"}}
    with pytest.raises(llm_client.LLMNoDisponible):
        llm_client.chat_completion(MSG, traza=_traza(db))
    f = _una(db)
    assert f.estado == "respuesta_invalida" and f.http_status == 200
    assert "modelo no disponible" in f.error and f.respuesta == {"error": {"message": "modelo no disponible"}}


def test_sin_api_key(db, llm_falso, monkeypatch):
    from pydantic import SecretStr

    monkeypatch.setattr(settings, "OPENROUTER_API_KEY", SecretStr(""))
    with pytest.raises(llm_client.LLMNoDisponible):
        llm_client.chat_completion(MSG, traza=_traza(db))
    f = _una(db)
    assert f.estado == "sin_configurar" and f.latencia_ms is None and llm_falso.llamadas == []


def test_la_api_key_nunca_se_guarda(db, llm_falso):
    clave = settings.OPENROUTER_API_KEY.get_secret_value()
    llm_falso.error = httpx.ConnectError(f"fallo con Authorization: Bearer {clave}")
    with pytest.raises(llm_client.LLMNoDisponible):
        llm_client.chat_completion(MSG, traza=_traza(db))
    llm_falso.error = None
    llm_client.chat_completion(MSG, traza=_traza(db))
    for f in _filas(db):
        assert clave not in json.dumps([f.request, f.respuesta, f.error])
        assert "Authorization" not in json.dumps(f.request)


# ── privacidad ──


def test_las_imagenes_se_guardan_como_huella(db, llm_falso):
    url = f"data:image/jpeg;base64,{base64.b64encode(JPEG).decode()}"
    mensajes = [{"role": "user", "content": [{"type": "text", "text": "mira"},
                                             {"type": "image_url", "image_url": {"url": url}}]}]  # fmt: skip
    llm_client.chat_completion(mensajes, traza=_traza(db, "vision"))
    f = _una(db)
    assert f.request["messages"][0]["content"][1] == {
        "imagen": {"sha256": hashlib.sha256(JPEG).hexdigest(), "bytes": len(JPEG), "mime": "image/jpeg"}}
    assert "base64" not in json.dumps(f.request) and base64.b64encode(JPEG).decode() not in json.dumps(f.request)
    assert llm_falso.llamadas[0]["payload"]["messages"][0]["content"][1]["image_url"]["url"] == url  # al proveedor sí


def test_guardar_contenido_false_solo_guarda_metadatos(db, llm_falso, monkeypatch):
    monkeypatch.setattr(settings, "LLM_TRAZA_GUARDAR_CONTENIDO", False)
    llm_falso.respuesta = _ok("respuesta privada", tool_calls=_tool("registrar_movimiento", {"cliente": "Rosa"}))
    llm_client.chat_completion(MSG, traza=_traza(db), tools=[{"type": "function", "function": {"name": "t"}}])
    f = _una(db)
    texto = json.dumps([f.request, f.respuesta])
    assert "vendí" not in texto and "privada" not in texto and "Rosa" not in texto
    assert "messages" not in f.request and f.request["n_messages"] == 1 and f.request["tools"] == ["t"]
    assert f.respuesta == {"finish_reason": "tool_calls", "tool_calls": [{"name": "registrar_movimiento"}]}
    assert (f.prompt_tokens, f.completion_tokens, f.total_tokens) == (120, 30, 150) and f.generation_id == "gen-abc123"


def test_traza_desactivada_no_escribe(db, llm_falso, monkeypatch):
    monkeypatch.setattr(settings, "LLM_TRAZA_ACTIVA", False)
    assert _traza(db) is None
    llm_client.chat_completion(MSG, traza=traza_llm.TrazaLLM(db, EMP, "extractor"))
    assert _filas(db) == []


def test_si_falla_el_guardado_el_flujo_sigue(db, llm_falso, monkeypatch, caplog):
    def _roto(*_a, **_k):
        raise RuntimeError("BD caída")

    monkeypatch.setattr(traza_llm, "nuevo_id", _roto)
    llm_falso.respuesta = _ok("hola")
    traza = _traza(db)
    assert llm_client.chat_completion(MSG, traza=traza)["content"] == "hola"
    assert traza.llamada_id is None and _filas(db) == []
    assert "No se pudo guardar la traza" in caplog.text
    traza.marcar("aceptada", referencia_tipo="borrador", referencia_id="BOR-0001")  # no rompe


def test_el_fallo_del_guardado_no_deja_la_sesion_rota(db, llm_falso, monkeypatch):
    original = m.LlmLlamada.__init__

    def _con_estado_invalido(self, *a, **k):
        original(self, *a, **k)
        self.estado = "inventado"  # viola el CHECK al hacer flush

    monkeypatch.setattr(m.LlmLlamada, "__init__", _con_estado_invalido)
    llm_client.chat_completion(MSG, traza=_traza(db))
    monkeypatch.undo()
    assert db.scalar(select(m.Empresa.empresa_id).limit(1)) is not None  # la sesión sigue usable


# ── consumidores ──


def test_extractor_enlaza_el_borrador_y_marca_aceptada(client_db, db, llm_falso):
    llm_falso.respuesta = _ok(None, tool_calls=_tool("registrar_movimiento", {
        "es_movimiento": True, "tipo": "venta", "items": [{"producto": "cerveza", "cantidad": 2}], "confianza": 0.9}))
    r = client_db.post(f"{P}/ingesta/interpretar", json={"empresa_id": EMP, "canal": "texto", "texto": "vendí dos cervezas"})
    assert r.status_code == 200, r.text
    f = _una(db)
    assert (f.origen, f.referencia_tipo, f.referencia_id) == ("extractor", "borrador", r.json()["borrador_id"])
    assert f.resultado_uso == "aceptada" and f.estado == "ok" and f.prompt_version == "extractor-v3"


def test_extractor_salida_invalida_marca_rechazada_validacion(client_db, db, llm_falso):
    llm_falso.respuesta = _ok(None, tool_calls=_tool("registrar_movimiento", {"es_movimiento": True, "monto": -5}))
    r = client_db.post(f"{P}/ingesta/interpretar", json={"empresa_id": EMP, "canal": "texto", "texto": "vendí dos cervezas"})
    assert r.status_code == 200 and r.json()["meta"]["fallback_usado"] is True
    f = _una(db)
    assert f.resultado_uso == "rechazada_validacion" and f.referencia_id == r.json()["borrador_id"]
    assert f.respuesta["tool_calls"][0]["function"]["name"] == "registrar_movimiento"  # respuesta cruda guardada


def test_extractor_llm_caido_enlaza_el_borrador_del_fallback(client_db, db, llm_falso):
    llm_falso.error = httpx.ReadTimeout("lento")
    r = client_db.post(f"{P}/ingesta/interpretar", json={"empresa_id": EMP, "canal": "texto", "texto": "vendí dos cervezas"})
    f = _una(db)
    assert f.estado == "timeout" and f.referencia_id == r.json()["borrador_id"] and f.resultado_uso is None


def test_extractor_no_interpretable_conserva_la_traza(client_db, db, llm_falso):
    llm_falso.respuesta = _ok(None, tool_calls=_tool("registrar_movimiento", {"es_movimiento": False, "tipo": None}))
    r = client_db.post(f"{P}/ingesta/interpretar", json={"empresa_id": EMP, "canal": "texto", "texto": "hola"})
    assert r.status_code == 422
    f = _una(db)
    assert f.resultado_uso == "aceptada" and f.referencia_id is None


def test_extractor_sin_db_no_traza(llm_falso):
    from app.services.ingesta import catalogo as cat_mod
    from app.services.ingesta import extractor

    llm_falso.respuesta = _ok(None, tool_calls=_tool("registrar_movimiento", {"es_movimiento": True, "tipo": "gasto_negocio",
                                                                              "monto": 80}))  # fmt: skip
    ext = extractor.extraer("pagué la luz, 80", empresa_id=EMP, catalogo=cat_mod.Catalogo(EMP))
    assert ext.llamada_id is None and ext.fallback_usado is False


def test_vlm_no_guarda_base64_y_enlaza_el_borrador(client_db, db, llm_falso, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "MEDIA_DIR", str(tmp_path))
    (tmp_path / "fotos").mkdir()
    (tmp_path / "fotos" / "nueva.jpg").write_bytes(JPEG)
    llm_falso.respuesta = _ok(None, tool_calls=_tool("registrar_fiados", {
        "fiados": [{"cliente": "Rosa", "monto": 12.5, "fecha": "2026-11-12", "tachado": False, "legible": True}],
        "lineas_no_legibles": 0}))  # fmt: skip
    r = client_db.post(f"{P}/ingesta/cuaderno", json={"empresa_id": EMP, "media_url": "demo://fotos/nueva.jpg"})
    assert r.status_code == 200, r.text
    f = _una(db)
    assert (f.origen, f.referencia_tipo, f.referencia_id) == ("vision", "borrador", r.json()["borrador_id"])
    assert f.resultado_uso == "aceptada" and f.modelo_solicitado == settings.VLM_MODEL
    texto = json.dumps(f.request)
    assert "base64" not in texto and base64.b64encode(JPEG).decode() not in texto
    imagen = f.request["messages"][1]["content"][1]["imagen"]
    assert imagen == {"sha256": hashlib.sha256(JPEG).hexdigest(), "bytes": len(JPEG), "mime": "image/jpeg"}


def _redactar(client_db, llm_falso, texto):
    llm_falso.respuesta = _ok(texto)
    return client_db.post(f"{P}/empresas/{EMP}/asistente/mensajes", json={"mensaje": "¿cómo va mi caja?"}).json()


def test_asistente_aceptada_enlaza_el_mensaje(client_db, db, llm_falso):
    d = _redactar(client_db, llm_falso, "Tienes S/ 2 340 en caja.")
    f = _una(db)
    asistente = db.query(m.Conversacion).filter_by(conversacion_id=d["conversacion_id"], rol="asistente").one()
    assert (f.origen, f.referencia_tipo, f.referencia_id) == ("asistente", "mensaje", asistente.mensaje_id)
    assert f.resultado_uso == "aceptada" and f.prompt_version == "asistente-v2"


def test_asistente_rechazada_por_el_verificador_guarda_la_respuesta_cruda(client_db, db, llm_falso):
    d = _redactar(client_db, llm_falso, "Tienes S/ 2 340 y te sobrarán S/ 4 321.")
    assert d["verificacion_cifras"]["ok"] is False
    f = _una(db)
    assert f.resultado_uso == "rechazada_verificador" and f.estado == "ok"
    assert f.respuesta["content"] == "Tienes S/ 2 340 y te sobrarán S/ 4 321."


def test_asistente_llm_caido_deja_la_fila_enlazada(client_db, db, llm_falso):
    llm_falso.error = httpx.ReadTimeout("lento")
    client_db.post(f"{P}/empresas/{EMP}/asistente/mensajes", json={"mensaje": "¿cómo va mi caja?"})
    f = _una(db)
    assert f.estado == "timeout" and f.referencia_tipo == "mensaje" and f.referencia_id.startswith("MSG-")


# ── endpoints ──


def _insertar(db, n, *, empresa=EMP, origen="extractor", estado="ok", uso=None, dt=None, tokens=(100, 20), costo="0.00001",
              ms=100):  # fmt: skip
    base = dt or ahora()
    for i in range(n):
        db.add(m.LlmLlamada(
            llamada_id=nuevo_id(db, m.LlmLlamada, "LLM", 6),
            empresa_id=empresa, origen=origen, proveedor="openrouter", modelo_solicitado="x", request={}, estado=estado,
            resultado_uso=uso, prompt_tokens=tokens[0], completion_tokens=tokens[1], total_tokens=sum(tokens),
            costo_usd=costo, latencia_ms=ms, creado_en=base + timedelta(seconds=i)))  # fmt: skip
        db.flush()


def test_listado_filtros_y_cursor(client_db, db):
    _insertar(db, 3, origen="extractor")
    _insertar(db, 2, origen="asistente", estado="timeout")
    r = client_db.get(f"{P}/empresas/{EMP}/llm/llamadas")
    assert r.status_code == 200
    cuerpo = r.json()
    assert len(cuerpo["items"]) == 5 and cuerpo["next_cursor"] is None and "request_id" in cuerpo["meta"]
    assert "request" not in cuerpo["items"][0] or cuerpo["items"][0]["request"] is None
    fechas = [i["creado_en"] for i in cuerpo["items"]]
    assert fechas == sorted(fechas, reverse=True)

    solo = client_db.get(f"{P}/empresas/{EMP}/llm/llamadas?origen=asistente&estado=timeout").json()["items"]
    assert len(solo) == 2 and {i["origen"] for i in solo} == {"asistente"}
    assert client_db.get(f"{P}/empresas/{EMP}/llm/llamadas?estado=ok").json()["items"].__len__() == 3

    p1 = client_db.get(f"{P}/empresas/{EMP}/llm/llamadas?limit=2").json()
    p2 = client_db.get(f"{P}/empresas/{EMP}/llm/llamadas?limit=2&cursor={p1['next_cursor']}").json()
    p3 = client_db.get(f"{P}/empresas/{EMP}/llm/llamadas?limit=2&cursor={p2['next_cursor']}").json()
    ids = [i["llamada_id"] for p in (p1, p2, p3) for i in p["items"]]
    assert len(ids) == 5 == len(set(ids)) and p3["next_cursor"] is None


def test_listado_por_fechas_contenido_y_validaciones(client_db, db):
    ayer = ahora() - timedelta(days=1)
    _insertar(db, 1, dt=ayer)
    _insertar(db, 1)
    hoy = ahora().date().isoformat()
    assert len(client_db.get(f"{P}/empresas/{EMP}/llm/llamadas?desde={hoy}").json()["items"]) == 1
    assert len(client_db.get(f"{P}/empresas/{EMP}/llm/llamadas?hasta={ayer.date().isoformat()}").json()["items"]) == 1
    con = client_db.get(f"{P}/empresas/{EMP}/llm/llamadas?incluir_contenido=true").json()["items"][0]
    assert con["request"] == {}
    assert client_db.get(f"{P}/empresas/{EMP}/llm/llamadas?origen=otro").status_code == 400
    assert client_db.get(f"{P}/empresas/{EMP}/llm/llamadas?cursor=basura").status_code == 400
    assert client_db.get(f"{P}/empresas/EMP-9999/llm/llamadas").status_code == 404
    assert client_db.get(f"{P}/empresas/EMP-9999/llm/resumen").status_code == 404


def test_listado_aislado_por_empresa(client_db, db):
    otra = m.Empresa(**{c.name: getattr(db.get(m.Empresa, EMP), c.name) for c in m.Empresa.__table__.columns})
    otra.empresa_id, otra.telefono_whatsapp, otra.nombre_ficticio = "EMP-0002", "+51999000002", "Otra bodega"
    db.add(otra)
    db.flush()
    _insertar(db, 2)
    _insertar(db, 3, empresa="EMP-0002")
    assert len(client_db.get(f"{P}/empresas/{EMP}/llm/llamadas").json()["items"]) == 2
    assert len(client_db.get(f"{P}/empresas/EMP-0002/llm/llamadas").json()["items"]) == 3
    assert client_db.get(f"{P}/empresas/EMP-0002/llm/resumen").json()["totales"]["llamadas"] == 3


def test_resumen_agregados_por_dia_y_origen(client_db, db):
    ayer = ahora() - timedelta(days=1)
    _insertar(db, 2, origen="extractor", ms=100, tokens=(100, 20), costo="0.00001")  # ok
    _insertar(db, 1, origen="extractor", estado="timeout", ms=300, tokens=(0, 0), costo="0")
    _insertar(db, 1, origen="asistente", uso="rechazada_verificador", ms=500, tokens=(200, 50), costo="0.00004")
    _insertar(db, 1, origen="asistente", uso="aceptada", ms=700, tokens=(100, 10), costo="0.00002", dt=ayer)
    r = client_db.get(f"{P}/empresas/{EMP}/llm/resumen")
    assert r.status_code == 200
    d = r.json()
    t = d["totales"]
    assert (t["llamadas"], t["ok"], t["errores"]) == (5, 4, 1)
    assert t["pct_fallback"] == 40.0  # 1 timeout + 1 rechazada por el verificador de 5
    assert (t["prompt_tokens"], t["completion_tokens"]) == (100 + 100 + 0 + 200 + 100, 20 + 20 + 0 + 50 + 10)
    assert t["costo_usd"] == pytest.approx(0.00001 * 2 + 0.00004 + 0.00002)
    assert t["latencia_p50_ms"] == 300 and t["latencia_p95_ms"] == 660  # [100, 100, 300, 500, 700]
    por_origen = {o["origen"]: o for o in d["por_origen"]}
    assert por_origen["extractor"]["llamadas"] == 3 and por_origen["extractor"]["errores"] == 1
    assert por_origen["extractor"]["pct_fallback"] == pytest.approx(33.3)
    assert por_origen["asistente"]["llamadas"] == 2 and por_origen["asistente"]["pct_fallback"] == 50.0
    dias = {x["fecha"]: x for x in d["por_dia"]}
    assert len(dias) == 2 and dias[ayer.date().isoformat()]["llamadas"] == 1
    assert dias[ahora().date().isoformat()]["llamadas"] == 4 and "request_id" in d["meta"]

    solo_hoy = client_db.get(f"{P}/empresas/{EMP}/llm/resumen?desde={ahora().date().isoformat()}").json()
    assert solo_hoy["totales"]["llamadas"] == 4 and len(solo_hoy["por_dia"]) == 1


def test_resumen_vacio(client_db):
    d = client_db.get(f"{P}/empresas/{EMP}/llm/resumen").json()
    assert d["totales"]["llamadas"] == 0 and d["totales"]["latencia_p50_ms"] is None and d["por_dia"] == []
    assert d["totales"]["pct_fallback"] == 0.0


def test_los_endpoints_exigen_api_key(client_sin_key):
    assert client_sin_key.get(f"{P}/empresas/{EMP}/llm/llamadas").status_code == 401
    assert client_sin_key.get(f"{P}/empresas/{EMP}/llm/resumen").status_code == 401

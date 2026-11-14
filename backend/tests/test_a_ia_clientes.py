"""services/ingesta/llm_client.py (OpenRouter) y transcriptor.py (faster-whisper perezoso). Nunca se llaman de verdad."""

import httpx
import pytest

from app.core.config import settings
from app.services.ingesta import estado_ia, llm_client, transcriptor


def test_sin_api_key_lanza_llm_no_disponible():
    with pytest.raises(llm_client.LLMNoDisponible, match="OPENROUTER_API_KEY"):
        llm_client.chat_completion([{"role": "user", "content": "hola"}])


def test_guardia_impide_llamar_al_llm_real(monkeypatch):
    from pydantic import SecretStr

    monkeypatch.setattr(settings, "OPENROUTER_API_KEY", SecretStr("sk-or-x"))
    with pytest.raises(AssertionError, match="LLM real"):
        llm_client.chat_completion([{"role": "user", "content": "hola"}])


def test_llamada_con_tools_devuelve_el_mensaje(llm_falso):
    llamada = {"id": "call_1", "type": "function",
               "function": {"name": "registrar_movimiento", "arguments": '{"tipo": "venta", "monto": 13}'}}  # fmt: skip
    llm_falso.respuesta = {"choices": [{"message": {"role": "assistant", "content": None, "tool_calls": [llamada]}}]}
    tools = [{"type": "function", "function": {"name": "registrar_movimiento", "parameters": {"type": "object"}}}]

    mensaje = llm_client.chat_completion([{"role": "user", "content": "vendí dos cervezas"}], tools=tools,
                                         tool_choice="auto")  # fmt: skip

    assert mensaje["tool_calls"][0]["function"]["name"] == "registrar_movimiento"
    enviado = llm_falso.llamadas[0]
    assert enviado["url"] == "https://openrouter.ai/api/v1/chat/completions"
    assert enviado["headers"]["Authorization"] == "Bearer sk-or-prueba"
    assert enviado["payload"]["model"] == settings.LLM_MODEL
    assert enviado["payload"]["tools"] == tools and enviado["payload"]["tool_choice"] == "auto"
    assert enviado["payload"]["temperature"] == settings.LLM_TEMPERATURE
    assert enviado["timeout"].read == settings.LLM_TIMEOUT_S


@pytest.mark.parametrize(
    "error",
    [
        httpx.ReadTimeout("lento"),
        httpx.HTTPStatusError("429", request=httpx.Request("POST", "https://x"),
                              response=httpx.Response(429, request=httpx.Request("POST", "https://x"))),
        httpx.ConnectError("sin red"),
    ],
    ids=["timeout", "http_429", "sin_red"],
)  # fmt: skip
def test_errores_de_red_se_vuelven_llm_no_disponible(llm_falso, error):
    llm_falso.error = error
    with pytest.raises(llm_client.LLMNoDisponible):
        llm_client.chat_completion([{"role": "user", "content": "hola"}])


def test_respuesta_sin_choices_es_controlada(llm_falso):
    llm_falso.respuesta = {"error": {"message": "modelo no disponible"}}
    with pytest.raises(llm_client.LLMNoDisponible, match="modelo no disponible"):
        llm_client.chat_completion([{"role": "user", "content": "hola"}])


def test_whisper_no_se_carga_al_importar_ni_en_health():
    assert not transcriptor.modelo_cargado()
    estado = estado_ia()
    assert estado["whisper"]["cargado"] is False
    assert estado["whisper"]["modelo"] == "faster-whisper-small"
    assert not transcriptor.modelo_cargado()


def test_guardia_impide_cargar_whisper_real():
    with pytest.raises(AssertionError, match="Whisper real"):
        transcriptor.transcribir("audio.ogg")


def test_transcribir_carga_una_sola_vez(whisper_falso):
    whisper_falso.texto = "vendí dos cervezas"
    assert transcriptor.transcribir("demo_001.ogg") == "vendí dos cervezas"
    assert transcriptor.transcribir("demo_002.ogg") == "vendí dos cervezas"
    assert whisper_falso.cargas == 1 and whisper_falso.archivos == ["demo_001.ogg", "demo_002.ogg"]
    assert transcriptor.modelo_cargado()


def test_estado_ia_llm_configurado(llm_falso):
    assert estado_ia()["llm"]["estado"] == "ok"
    assert llm_falso.llamadas == []  # el health no llama a la red

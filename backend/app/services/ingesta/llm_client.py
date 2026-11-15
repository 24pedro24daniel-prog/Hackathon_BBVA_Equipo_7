"""Cliente mínimo de OpenRouter (API compatible con OpenAI: /chat/completions con `tools`).

    mensaje = chat_completion([{"role": "user", "content": "vendí dos cervezas"}], tools=[...])
    mensaje["tool_calls"] / mensaje["content"]

Lanza LLMNoDisponible si no hay OPENROUTER_API_KEY, si hay timeout o si el proveedor responde con error;
quien llama decide el fallback (reglas/plantillas) y marca `meta.fallback_usado = true`.

Con `traza` (ver traza_llm.py) cada llamada deja una fila en `llm_llamadas`, también si falla.
"""

import time
from typing import Any

import httpx

from app.core.config import settings
from app.services.ingesta.traza_llm import TrazaLLM


class LLMNoDisponible(Exception):
    """El LLM no está configurado o no respondió bien. Usar el fallback."""


def _headers() -> dict[str, str]:
    clave = settings.OPENROUTER_API_KEY.get_secret_value().strip()
    if not clave:
        raise LLMNoDisponible("OPENROUTER_API_KEY no está configurada")
    return {
        "Authorization": f"Bearer {clave}",
        "Content-Type": "application/json",
        "HTTP-Referer": settings.LLM_APP_URL,
        "X-Title": settings.LLM_APP_NAME,
    }


def _post(url: str, payload: dict[str, Any], headers: dict[str, str], timeout: httpx.Timeout) -> dict[str, Any]:
    """Única función que sale a la red (los tests la reemplazan)."""
    with httpx.Client(timeout=timeout) as cliente:
        r = cliente.post(url, json=payload, headers=headers)
        r.raise_for_status()
        return r.json()


def chat_completion(
    messages: list[dict[str, Any]],
    *,
    tools: list[dict[str, Any]] | None = None,
    tool_choice: str | dict[str, Any] | None = None,
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    response_format: dict[str, Any] | None = None,
    timeout_s: float | None = None,
    traza: TrazaLLM | None = None,
) -> dict[str, Any]:
    """Hace una llamada y devuelve `choices[0].message` (dict con role, content y quizá tool_calls)."""
    payload: dict[str, Any] = {
        "model": model or settings.LLM_MODEL,
        "messages": messages,
        "temperature": settings.LLM_TEMPERATURE if temperature is None else temperature,
        "max_tokens": max_tokens or settings.LLM_MAX_TOKENS,
        "usage": {"include": True},  # OpenRouter devuelve tokens y costo en la respuesta
    }
    if tools:
        payload["tools"] = tools
        if tool_choice is not None:
            payload["tool_choice"] = tool_choice
    if response_format:
        payload["response_format"] = response_format

    def registrar(estado: str, inicio: float | None = None, **kw: Any) -> None:
        if traza is not None and settings.LLM_TRAZA_ACTIVA:
            ms = None if inicio is None else int((time.perf_counter() - inicio) * 1000)
            traza.registrar(payload, estado=estado, latencia_ms=ms, **kw)

    try:
        headers = _headers()
    except LLMNoDisponible as exc:
        registrar("sin_configurar", error=str(exc))
        raise

    limite = timeout_s or settings.LLM_TIMEOUT_S
    timeout = httpx.Timeout(limite, connect=min(5.0, limite))
    url = settings.LLM_BASE_URL.rstrip("/") + "/chat/completions"
    inicio = time.perf_counter()
    try:
        datos = _post(url, payload, headers, timeout)
    except httpx.TimeoutException as exc:
        registrar("timeout", inicio, error=f"Timeout a los {limite:.0f} s")
        raise LLMNoDisponible(f"El LLM no respondió en {limite:.0f} s") from exc
    except httpx.HTTPStatusError as exc:
        estado_http = exc.response.status_code
        registrar("http_error", inicio, http_status=estado_http, error=f"HTTP {estado_http}: {_motivo(exc.response)}")
        raise LLMNoDisponible(f"El LLM respondió {estado_http}") from exc
    except httpx.HTTPError as exc:
        registrar("red", inicio, error=f"{type(exc).__name__}: {exc}")
        raise LLMNoDisponible(f"Error de red con el LLM: {exc}") from exc
    except ValueError as exc:  # el cuerpo no era JSON
        registrar("respuesta_invalida", inicio, http_status=200, error=f"Cuerpo no JSON: {exc}")
        raise LLMNoDisponible(f"Error de red con el LLM: {exc}") from exc

    try:
        mensaje = datos["choices"][0]["message"]
    except (KeyError, IndexError, TypeError) as exc:
        error = datos.get("error") if isinstance(datos, dict) else None
        registrar("respuesta_invalida", inicio, http_status=200, datos=datos,
                  error=f"Respuesta inesperada: {error or 'sin choices'}")  # fmt: skip
        raise LLMNoDisponible(f"Respuesta inesperada del LLM: {error or 'sin choices'}") from exc
    registrar("ok", inicio, http_status=200, datos=datos)
    return mensaje


def _motivo(respuesta: httpx.Response) -> str:
    """Mensaje de error del proveedor (sin secretos) para la traza."""
    try:
        cuerpo = respuesta.json()
        error = cuerpo.get("error") if isinstance(cuerpo, dict) else None
        return str(error.get("message") if isinstance(error, dict) else error or cuerpo)[:200]
    except Exception:  # noqa: BLE001
        try:
            return respuesta.text[:200]
        except Exception:  # noqa: BLE001
            return ""

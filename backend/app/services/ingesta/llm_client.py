"""Cliente mínimo de OpenRouter (API compatible con OpenAI: /chat/completions con `tools`).

    mensaje = chat_completion([{"role": "user", "content": "vendí dos cervezas"}], tools=[...])
    mensaje["tool_calls"] / mensaje["content"]

Lanza LLMNoDisponible si no hay OPENROUTER_API_KEY, si hay timeout o si el proveedor responde con error;
quien llama decide el fallback (reglas/plantillas) y marca `meta.fallback_usado = true`.
"""

from typing import Any

import httpx

from app.core.config import settings


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
) -> dict[str, Any]:
    """Hace una llamada y devuelve `choices[0].message` (dict con role, content y quizá tool_calls)."""
    headers = _headers()
    payload: dict[str, Any] = {
        "model": model or settings.LLM_MODEL,
        "messages": messages,
        "temperature": settings.LLM_TEMPERATURE if temperature is None else temperature,
        "max_tokens": max_tokens or settings.LLM_MAX_TOKENS,
    }
    if tools:
        payload["tools"] = tools
        if tool_choice is not None:
            payload["tool_choice"] = tool_choice
    if response_format:
        payload["response_format"] = response_format

    limite = timeout_s or settings.LLM_TIMEOUT_S
    timeout = httpx.Timeout(limite, connect=min(5.0, limite))
    url = settings.LLM_BASE_URL.rstrip("/") + "/chat/completions"
    try:
        datos = _post(url, payload, headers, timeout)
    except httpx.TimeoutException as exc:
        raise LLMNoDisponible(f"El LLM no respondió en {limite:.0f} s") from exc
    except httpx.HTTPStatusError as exc:
        raise LLMNoDisponible(f"El LLM respondió {exc.response.status_code}") from exc
    except (httpx.HTTPError, ValueError) as exc:
        raise LLMNoDisponible(f"Error de red con el LLM: {exc}") from exc

    try:
        return datos["choices"][0]["message"]
    except (KeyError, IndexError, TypeError) as exc:
        error = datos.get("error") if isinstance(datos, dict) else None
        raise LLMNoDisponible(f"Respuesta inesperada del LLM: {error or 'sin choices'}") from exc

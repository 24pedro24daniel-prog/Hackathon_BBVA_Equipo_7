"""Bloque `meta` de las respuestas con salida de modelo + request_id por petición."""
import time
import uuid
from contextvars import ContextVar

from app.core.reloj import ahora
from app.schemas.common import Meta

_request_id: ContextVar[str] = ContextVar("request_id", default="req_sin_contexto")
_inicio: ContextVar[float] = ContextVar("inicio_peticion", default=0.0)


def iniciar_peticion() -> str:
    """La llama el middleware de main.py al comenzar cada petición."""
    rid = f"req_{uuid.uuid4().hex[:6]}"
    _request_id.set(rid)
    _inicio.set(time.perf_counter())
    return rid


def request_id_actual() -> str:
    return _request_id.get()


def construir_meta(
    modelo: str,
    modelo_version: str,
    *,
    prompt_version: str | None = None,
    fallback_usado: bool = False,
) -> Meta:
    ini = _inicio.get()
    latencia = int((time.perf_counter() - ini) * 1000) if ini else 0
    return Meta(
        request_id=request_id_actual(),
        generado_en=ahora(),
        modelo=modelo,
        modelo_version=modelo_version,
        prompt_version=prompt_version,
        fallback_usado=fallback_usado,
        latencia_ms=latencia,
    )

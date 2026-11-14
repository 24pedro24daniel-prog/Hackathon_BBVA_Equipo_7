"""Bloque `meta` del contrato y request_id por solicitud.

El middleware de main.py fija el request_id y el instante de inicio en un ContextVar, así cualquier
servicio puede construir el `meta` sin recibir el Request.
"""

import secrets
import time
from contextvars import ContextVar

from app.schemas.common import Meta

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
_inicio: ContextVar[float | None] = ContextVar("inicio", default=None)


def nuevo_request_id() -> str:
    return f"req_{secrets.token_hex(3)}"


def iniciar_request(request_id: str | None = None) -> str:
    rid = request_id or nuevo_request_id()
    _request_id.set(rid)
    _inicio.set(time.perf_counter())
    return rid


def request_id_actual() -> str:
    rid = _request_id.get()
    return rid if rid else nuevo_request_id()


def latencia_ms() -> int | None:
    inicio = _inicio.get()
    return None if inicio is None else int((time.perf_counter() - inicio) * 1000)


def construir_meta(
    modelo: str | None,
    modelo_version: str | None,
    *,
    prompt_version: str | None = None,
    fallback_usado: bool = False,
) -> Meta:
    from app.core.reloj import ahora

    return Meta(
        request_id=request_id_actual(),
        generado_en=ahora(),
        modelo=modelo,
        modelo_version=modelo_version,
        prompt_version=prompt_version,
        fallback_usado=fallback_usado,
        latencia_ms=latencia_ms(),
    )

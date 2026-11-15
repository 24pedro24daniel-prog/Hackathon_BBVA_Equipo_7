"""Observabilidad del LLM (interno): listado de llamadas y resumen de uso/costo."""

from datetime import date, datetime
from enum import Enum
from typing import Any

from app.schemas.common import Meta, ModeloContrato


class OrigenLLM(str, Enum):
    extractor = "extractor"
    asistente = "asistente"
    vision = "vision"


class EstadoLLM(str, Enum):
    ok = "ok"
    timeout = "timeout"
    http_error = "http_error"
    red = "red"
    respuesta_invalida = "respuesta_invalida"
    sin_configurar = "sin_configurar"


class LlamadaLLM(ModeloContrato):
    llamada_id: str
    origen: str
    referencia_tipo: str | None = None
    referencia_id: str | None = None
    prompt_version: str | None = None
    proveedor: str
    modelo_solicitado: str | None = None
    modelo_respondido: str | None = None
    generation_id: str | None = None
    estado: str
    http_status: int | None = None
    error: str | None = None
    resultado_uso: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    costo_usd: float | None = None
    latencia_ms: int | None = None
    creado_en: datetime
    request: Any | None = None
    respuesta: Any | None = None


class LlamadasResponse(ModeloContrato):
    items: list[LlamadaLLM]
    next_cursor: str | None = None
    meta: Meta


class AgregadoLLM(ModeloContrato):
    llamadas: int
    ok: int
    errores: int
    pct_fallback: float
    prompt_tokens: int
    completion_tokens: int
    costo_usd: float
    latencia_p50_ms: int | None = None
    latencia_p95_ms: int | None = None


class AgregadoPorDia(AgregadoLLM):
    fecha: date


class AgregadoPorOrigen(AgregadoLLM):
    origen: str


class ResumenLLMResponse(ModeloContrato):
    desde: date | None = None
    hasta: date | None = None
    totales: AgregadoLLM
    por_dia: list[AgregadoPorDia]
    por_origen: list[AgregadoPorOrigen]
    meta: Meta

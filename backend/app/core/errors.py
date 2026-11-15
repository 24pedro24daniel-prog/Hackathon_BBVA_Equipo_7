"""Errores con el formato del contrato: {"error": {codigo, mensaje, detalles, request_id}}."""

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.meta import request_id_actual

log = logging.getLogger("cajaclara")

CODIGO_POR_STATUS = {
    400: "VALIDACION",
    401: "NO_AUTORIZADO",
    404: "NO_ENCONTRADO",
    403: "EMPRESA_NO_PERMITIDA",
    405: "METODO_NO_PERMITIDO",
    409: "CONFLICTO",
    422: "NO_INTERPRETABLE",
    429: "DEMASIADOS_INTENTOS",
    503: "SERVICIO_NO_DISPONIBLE",
}


class ErrorAPI(Exception):
    def __init__(self, status: int, codigo: str, mensaje: str, detalles: list[dict[str, Any]] | None = None,
                 headers: dict[str, str] | None = None):  # fmt: skip
        super().__init__(mensaje)
        self.status = status
        self.codigo = codigo
        self.mensaje = mensaje
        self.detalles = detalles or []
        self.headers = headers


class NoEncontrado(ErrorAPI):
    def __init__(self, mensaje: str = "No encontré ese registro.", detalles=None):
        super().__init__(404, "NO_ENCONTRADO", mensaje, detalles)


class Conflicto(ErrorAPI):
    def __init__(self, mensaje: str, detalles=None):
        super().__init__(409, "CONFLICTO", mensaje, detalles)


class Validacion(ErrorAPI):
    def __init__(self, mensaje: str, detalles=None):
        super().__init__(400, "VALIDACION", mensaje, detalles)


class NoInterpretable(ErrorAPI):
    def __init__(self, mensaje: str, detalles=None):
        super().__init__(422, "NO_INTERPRETABLE", mensaje, detalles)


class ServicioNoDisponible(ErrorAPI):
    def __init__(self, mensaje: str, detalles=None):
        super().__init__(503, "SERVICIO_NO_DISPONIBLE", mensaje, detalles)


def cuerpo_error(codigo: str, mensaje: str, detalles: list | None = None) -> dict:
    return {"error": {"codigo": codigo, "mensaje": mensaje, "detalles": detalles or [], "request_id": request_id_actual()}}


def respuesta_error(status: int, codigo: str, mensaje: str, detalles: list | None = None, headers=None) -> JSONResponse:
    return JSONResponse(status_code=status, content=cuerpo_error(codigo, mensaje, detalles), headers=headers)


def _problema_es(e: dict) -> str:
    """Mensaje de validación de pydantic en español, sin jerga ("Input should be…" no llega al usuario)."""
    tipo, ctx = e.get("type", ""), e.get("ctx") or {}
    if tipo == "missing":
        return "es obligatorio"
    if tipo in ("greater_than", "greater_than_equal", "less_than", "less_than_equal"):
        limite = ctx.get({"greater_than": "gt", "greater_than_equal": "ge", "less_than": "lt", "less_than_equal": "le"}[tipo])
        texto = {"greater_than": "debe ser mayor que", "greater_than_equal": "debe ser al menos",
                 "less_than": "debe ser menor que", "less_than_equal": "debe ser como máximo"}[tipo]
        return f"{texto} {limite}"
    if tipo == "enum":
        return f"valor no permitido (usa: {ctx.get('expected', '').replace(chr(39), '')})"
    if tipo == "literal_error":
        return f"valor no permitido (usa: {ctx.get('expected', '').replace(chr(39), '')})"
    if tipo == "string_too_short":
        return f"debe tener al menos {ctx.get('min_length')} caracteres"
    if tipo == "string_too_long":
        return f"debe tener como máximo {ctx.get('max_length')} caracteres"
    if tipo == "string_pattern_mismatch":
        return "no tiene el formato esperado"
    if tipo == "extra_forbidden":
        return "campo no permitido"
    if tipo in ("int_parsing", "int_from_float", "int_type"):
        return "debe ser un número entero"
    if tipo in ("float_parsing", "float_type", "decimal_parsing", "decimal_type", "decimal_max_digits",
                "decimal_max_places", "decimal_whole_digits"):
        return "debe ser un número"
    if tipo in ("string_type", "str_type"):
        return "debe ser texto"
    if tipo in ("bool_parsing", "bool_type"):
        return "debe ser verdadero o falso"
    if tipo in ("date_parsing", "date_type", "date_from_datetime_parsing"):
        return "debe ser una fecha válida (AAAA-MM-DD)"
    if tipo in ("datetime_parsing", "datetime_type"):
        return "debe ser una fecha y hora válidas"
    if tipo in ("list_type", "tuple_type"):
        return "debe ser una lista"
    if tipo in ("dict_type", "model_type", "model_attributes_type"):
        return "debe ser un objeto"
    if tipo == "json_invalid":
        return "el JSON enviado no es válido"
    if tipo == "too_short":
        return f"debe tener al menos {ctx.get('min_length')} elemento(s)"
    if tipo == "too_long":
        return f"debe tener como máximo {ctx.get('max_length')} elemento(s)"
    return "no es válido"


def _detalles_validacion(exc: RequestValidationError) -> list[dict[str, str]]:
    detalles = []
    for e in exc.errors():
        loc = [str(p) for p in e.get("loc", ()) if p not in ("body", "query", "path", "header")]
        detalles.append({"campo": ".".join(loc) or "payload", "problema": _problema_es(e)})
    return detalles


def registrar_handlers(app: FastAPI) -> None:
    @app.exception_handler(ErrorAPI)
    async def _error_api(_: Request, exc: ErrorAPI):
        return respuesta_error(exc.status, exc.codigo, exc.mensaje, exc.detalles, headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def _validacion(_: Request, exc: RequestValidationError):
        detalles = _detalles_validacion(exc)
        primero = detalles[0] if detalles else {"campo": "payload", "problema": "inválido"}
        mensaje = f"El campo '{primero['campo']}' no es válido: {primero['problema']}."
        return respuesta_error(400, "VALIDACION", mensaje, detalles)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException):
        codigo = CODIGO_POR_STATUS.get(exc.status_code, "ERROR")
        mensaje = exc.detail if isinstance(exc.detail, str) else "Error en la solicitud."
        if exc.status_code == 404 and mensaje == "Not Found":
            mensaje = "Ruta no encontrada."
        return respuesta_error(exc.status_code, codigo, mensaje, headers=getattr(exc, "headers", None))

    @app.exception_handler(Exception)
    async def _inesperado(_: Request, exc: Exception):
        log.exception("Error no controlado: %s", exc)
        return respuesta_error(500, "ERROR_INTERNO", "Ocurrió un error inesperado. Intenta otra vez.")

"""Errores con el formato del contrato:
{ "error": { "codigo", "mensaje", "detalles", "request_id" } }
"""
import logging
from enum import StrEnum

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.meta import request_id_actual

log = logging.getLogger("cajaclara")


class Codigo(StrEnum):
    VALIDACION = "VALIDACION"                          # 400
    NO_AUTORIZADO = "NO_AUTORIZADO"                    # 401
    NO_ENCONTRADO = "NO_ENCONTRADO"                    # 404
    CONFLICTO = "CONFLICTO"                            # 409
    NO_INTERPRETABLE = "NO_INTERPRETABLE"              # 422
    SERVICIO_NO_DISPONIBLE = "SERVICIO_NO_DISPONIBLE"  # 503
    ERROR_INTERNO = "ERROR_INTERNO"                    # 500


_STATUS = {
    Codigo.VALIDACION: 400,
    Codigo.NO_AUTORIZADO: 401,
    Codigo.NO_ENCONTRADO: 404,
    Codigo.CONFLICTO: 409,
    Codigo.NO_INTERPRETABLE: 422,
    Codigo.SERVICIO_NO_DISPONIBLE: 503,
    Codigo.ERROR_INTERNO: 500,
}


class ApiError(Exception):
    """Lanzar desde cualquier router/servicio: raise ApiError(Codigo.NO_ENCONTRADO, "No existe ...")."""

    def __init__(self, codigo: Codigo, mensaje: str, detalles: list[dict] | None = None):
        super().__init__(mensaje)
        self.codigo = codigo
        self.mensaje = mensaje
        self.detalles = detalles or []
        self.status = _STATUS[codigo]


def _respuesta(status: int, codigo: str, mensaje: str, detalles: list | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={
            "error": {
                "codigo": codigo,
                "mensaje": mensaje,
                "detalles": detalles or [],
                "request_id": request_id_actual(),
            }
        },
    )


def registrar_errores(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError):
        return _respuesta(exc.status, exc.codigo.value, exc.mensaje, exc.detalles)

    @app.exception_handler(RequestValidationError)
    async def _validacion(_: Request, exc: RequestValidationError):
        detalles = [
            {"campo": ".".join(str(p) for p in e["loc"] if p not in ("body", "query", "path")),
             "problema": e["msg"]}
            for e in exc.errors()
        ]
        campo = detalles[0]["campo"] if detalles else ""
        msg = f"El campo '{campo}' no es válido." if campo else "Datos inválidos."
        return _respuesta(400, Codigo.VALIDACION.value, msg, detalles)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException):
        codigo = {401: Codigo.NO_AUTORIZADO, 404: Codigo.NO_ENCONTRADO, 409: Codigo.CONFLICTO}.get(
            exc.status_code, Codigo.ERROR_INTERNO if exc.status_code >= 500 else Codigo.VALIDACION
        )
        return _respuesta(exc.status_code, codigo.value, str(exc.detail))

    @app.exception_handler(Exception)
    async def _inesperado(_: Request, exc: Exception):
        log.exception("Error no controlado", exc_info=exc)
        return _respuesta(500, Codigo.ERROR_INTERNO.value, "Ocurrió un error inesperado.")

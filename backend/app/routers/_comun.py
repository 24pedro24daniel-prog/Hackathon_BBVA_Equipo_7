"""Piezas compartidas por los routers."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path

from app.core.auth import limitar_ia, verificar_acceso
from app.schemas.common import ErrorResponse

EmpresaId = Annotated[str, Path(pattern=r"^EMP-\d{4,}$", description="ID de la empresa, p. ej. EMP-0001")]

RESPUESTAS_ERROR = {
    400: {"model": ErrorResponse, "description": "VALIDACION"},
    401: {"model": ErrorResponse, "description": "NO_AUTORIZADO / SESION_EXPIRADA"},
    403: {"model": ErrorResponse, "description": "EMPRESA_NO_PERMITIDA (Bearer de otra empresa)"},
    404: {"model": ErrorResponse, "description": "NO_ENCONTRADO"},
}


# Rutas que gastan LLM/VLM/Whisper/R2: límite de usos por sesión y por usuario (429 DEMASIADOS_INTENTOS + Retry-After)
CON_LIMITE_IA = [Depends(limitar_ia)]


def router_protegido(tag: str) -> APIRouter:
    """Router cuyas rutas exigen Bearer (solo su empresa) o X-API-Key."""
    return APIRouter(tags=[tag], dependencies=[Depends(verificar_acceso)], responses=RESPUESTAS_ERROR)

"""Piezas compartidas por los routers."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path

from app.core.auth import verificar_api_key
from app.schemas.common import ErrorResponse

EmpresaId = Annotated[str, Path(pattern=r"^EMP-\d{4,}$", description="ID de la empresa, p. ej. EMP-0001")]

RESPUESTAS_ERROR = {
    400: {"model": ErrorResponse, "description": "VALIDACION"},
    401: {"model": ErrorResponse, "description": "NO_AUTORIZADO"},
    404: {"model": ErrorResponse, "description": "NO_ENCONTRADO"},
}


def router_protegido(tag: str) -> APIRouter:
    """Router cuyas rutas exigen X-API-Key."""
    return APIRouter(tags=[tag], dependencies=[Depends(verificar_api_key)], responses=RESPUESTAS_ERROR)

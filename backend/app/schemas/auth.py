"""Login de las demos (contract.md §12)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import ModeloContrato


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)

    usuario: str = Field(min_length=1, max_length=64)
    contrasena: str = Field(min_length=1, max_length=128)


class Negocio(ModeloContrato):
    nombre: str


class LoginResponse(ModeloContrato):
    token: str
    tipo: Literal["Bearer"] = "Bearer"
    expira_en: int
    expira: datetime
    usuario: str
    empresa_id: str
    negocio: Negocio


class SesionResponse(ModeloContrato):
    usuario: str
    empresa_id: str
    expira: datetime
    negocio: Negocio

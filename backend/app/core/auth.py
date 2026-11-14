"""Dependencia X-API-Key. La clave vive en .env (API_KEY). Si está vacía, no se exige (solo dev)."""
import secrets

from fastapi import Header

from app.core.config import get_settings
from app.core.errors import ApiError, Codigo


def verificar_api_key(x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> None:
    esperada = get_settings().API_KEY
    if not esperada:
        return
    if not x_api_key or not secrets.compare_digest(x_api_key, esperada):
        raise ApiError(Codigo.NO_AUTORIZADO, "Falta la API key o no es válida.")

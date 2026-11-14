"""Autenticación de la demo: header X-API-Key contra API_KEY de .env (contrato §0)."""

import secrets

from fastapi import Header

from app.core.config import settings
from app.core.errors import ErrorAPI


def verificar_api_key(x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> None:
    esperada = settings.API_KEY.get_secret_value()
    if not x_api_key:
        raise ErrorAPI(401, "NO_AUTORIZADO", "Falta el header X-API-Key.")
    if not esperada or not secrets.compare_digest(x_api_key.encode(), esperada.encode()):
        raise ErrorAPI(401, "NO_AUTORIZADO", "La API key no es válida.")

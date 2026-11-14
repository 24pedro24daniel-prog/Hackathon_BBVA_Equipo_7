"""Paginación por cursor opaco (?limit=50&cursor=<token>) -> { items, next_cursor }."""
import base64
import json
from collections.abc import Callable
from typing import Any

from fastapi import Query

from app.core.errors import ApiError, Codigo


def codificar_cursor(datos: dict[str, Any]) -> str:
    raw = json.dumps(datos, separators=(",", ":"), default=str).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decodificar_cursor(token: str | None) -> dict[str, Any] | None:
    if not token:
        return None
    try:
        relleno = "=" * (-len(token) % 4)
        return json.loads(base64.urlsafe_b64decode(token + relleno))
    except Exception:
        raise ApiError(Codigo.VALIDACION, "El cursor no es válido.", [{"campo": "cursor", "problema": "inválido"}])


class Paginacion:
    """Dependencia: def endpoint(pag: Paginacion = Depends()). Usa pag.limit y pag.cursor (dict|None)."""

    def __init__(self, limit: int = Query(50, ge=1, le=200), cursor: str | None = Query(None)):
        self.limit = limit
        self.cursor = decodificar_cursor(cursor)


def armar_pagina(filas: list, limit: int, cursor_de: Callable[[Any], dict]) -> tuple[list, str | None]:
    """Pedir a la BD `limit + 1` filas; devuelve (items, next_cursor)."""
    if len(filas) > limit:
        items = filas[:limit]
        return items, codificar_cursor(cursor_de(items[-1]))
    return filas, None

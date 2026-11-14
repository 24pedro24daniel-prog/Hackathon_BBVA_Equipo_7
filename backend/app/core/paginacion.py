"""Paginación por cursor del contrato: ?limit=50&cursor=<token> → next_cursor (null si no hay más).

El cursor es opaco para el cliente: JSON en base64url con la clave de orden del último ítem.
"""

import base64
import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, TypeVar

from fastapi import Query

from app.core.errors import Validacion

T = TypeVar("T")

LIMITE_POR_DEFECTO = 50
LIMITE_MAXIMO = 200


@dataclass
class Pagina:
    limit: int
    cursor: dict[str, Any] | None


def codificar_cursor(datos: dict[str, Any]) -> str:
    crudo = json.dumps(datos, separators=(",", ":"), default=str).encode()
    return base64.urlsafe_b64encode(crudo).decode().rstrip("=")


def decodificar_cursor(token: str) -> dict[str, Any]:
    try:
        relleno = "=" * (-len(token) % 4)
        datos = json.loads(base64.urlsafe_b64decode(token + relleno))
    except (ValueError, json.JSONDecodeError) as exc:
        raise Validacion("El cursor no es válido.", [{"campo": "cursor", "problema": "formato inválido"}]) from exc
    if not isinstance(datos, dict):
        raise Validacion("El cursor no es válido.", [{"campo": "cursor", "problema": "formato inválido"}])
    return datos


def parametros_pagina(
    limit: int = Query(LIMITE_POR_DEFECTO, ge=1, le=LIMITE_MAXIMO),
    cursor: str | None = Query(None),
) -> Pagina:
    return Pagina(limit=limit, cursor=decodificar_cursor(cursor) if cursor else None)


def recortar(items: Sequence[T], limit: int, clave: Callable[[T], dict[str, Any]]) -> tuple[list[T], str | None]:
    """Recibe hasta limit + 1 ítems ya ordenados; devuelve (página, next_cursor)."""
    if len(items) <= limit:
        return list(items), None
    pagina = list(items[:limit])
    return pagina, codificar_cursor(clave(pagina[-1]))

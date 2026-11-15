"""TuCaserito API. Arranque: uvicorn app.main:app --port 8000 --reload --no-proxy-headers

Registra TODOS los routers. Autenticación (contract.md §0 y §12): /health y /auth/login son públicas; el resto exige
`Authorization: Bearer <token>` (sesión de una empresa) o `X-API-Key` (bot/admin), ver app/core/auth.py.
"""
import logging

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.auth import verificar_acceso
from app.core.config import settings
from app.core.errors import registrar_handlers
from app.core.meta import iniciar_request
from app.routers import (
    alertas, analisis, asistente, auth, chat, fiados, forecast, health, ingesta,
    impuestos, llm_trazas, media, movimientos, pedidos, resumen, salud, simulador, webhooks,
)

PREFIJO = settings.API_PREFIX


class RequestIdMiddleware:
    """Fija request_id e instante de inicio (para `meta`) y devuelve el header X-Request-ID.

    ASGI puro (no BaseHTTPMiddleware): el request_id sigue visible en los handlers de error 500.
    """

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        entrante = dict(scope.get("headers") or []).get(b"x-request-id")
        rid = iniciar_request(entrante.decode()[:64] if entrante else None)

        async def enviar(message: Message) -> None:
            if message["type"] == "http.response.start":
                message.setdefault("headers", [])
                message["headers"].append((b"x-request-id", rid.encode()))
            await send(message)

        await self.app(scope, receive, enviar)


logging.basicConfig(level=settings.LOG_LEVEL)

# CORS (contract.md §12): sin cookies; el front manda el token en Authorization. Retry-After se expone para que el front
# pueda leerlo en los 429.
CORS_METODOS = ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
CORS_HEADERS = ["Authorization", "Content-Type", "Idempotency-Key", "X-API-Key"]
CORS_EXPUESTOS = ["X-Request-ID", "Retry-After"]

# Protegidas: Bearer (solo su empresa) o X-API-Key
PROTEGIDOS = [
    # Dev A
    webhooks.router, ingesta.router, chat.router, media.router, impuestos.router, movimientos.router, asistente.router, salud.router,
    # Dev B
    resumen.router, forecast.router, fiados.router, pedidos.router, simulador.router,
    analisis.router, alertas.router,
    # Observabilidad interna
    llm_trazas.router,
]


def crear_app(cors_origenes: list[str] | None = None) -> FastAPI:
    aplicacion = FastAPI(title="TuCaserito API", version=settings.API_VERSION, docs_url="/docs", redoc_url=None)
    aplicacion.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins if cors_origenes is None else cors_origenes,
        allow_methods=CORS_METODOS,
        allow_headers=CORS_HEADERS,
        allow_credentials=False,
        expose_headers=CORS_EXPUESTOS,
        max_age=600,
    )
    aplicacion.add_middleware(RequestIdMiddleware)
    registrar_handlers(aplicacion)

    # Públicas: monitoreo y login (GET /auth/sesion exige Bearer por su cuenta)
    aplicacion.include_router(health.router, prefix=PREFIJO)
    aplicacion.include_router(auth.router, prefix=PREFIJO)
    for r in PROTEGIDOS:
        aplicacion.include_router(r, prefix=PREFIJO, dependencies=[Depends(verificar_acceso)])
    return aplicacion


app = crear_app()

"""CajaClara API (FastAPI). Registra TODOS los routers del plan bajo /api/v1.

    uvicorn app.main:app --port 8000
"""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import settings
from app.core.errors import registrar_handlers
from app.core.meta import iniciar_request
from app.routers import (
    alertas,
    analisis,
    asistente,
    fiados,
    forecast,
    health,
    impuestos,
    ingesta,
    movimientos,
    pedidos,
    resumen,
    salud,
    simulador,
    webhooks,
)

ROUTERS = [
    # Dev A — ingesta y conversación
    webhooks.router,
    ingesta.router,
    impuestos.router,
    movimientos.router,
    asistente.router,
    salud.router,
    # Dev B — motores financieros
    resumen.router,
    forecast.router,
    fiados.router,
    pedidos.router,
    simulador.router,
    analisis.router,
    alertas.router,
    health.router,
]


class RequestIdMiddleware:
    """Fija request_id e instante de inicio (para `meta`) y devuelve el header X-Request-ID."""

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


def create_app() -> FastAPI:
    logging.basicConfig(level=settings.LOG_LEVEL)
    app = FastAPI(
        title="CajaClara API",
        version=settings.API_VERSION,
        description="Gestor financiero para bodegas. Contrato: contract.md. Todos los datos son sintéticos.",
        openapi_url=f"{settings.API_PREFIX}/openapi.json",
        docs_url=f"{settings.API_PREFIX}/docs",
        redoc_url=None,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "OPTIONS"],
        allow_headers=["Content-Type", "X-API-Key", "Idempotency-Key", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )
    app.add_middleware(RequestIdMiddleware)
    registrar_handlers(app)
    for router in ROUTERS:
        app.include_router(router, prefix=settings.API_PREFIX)
    return app


app = create_app()

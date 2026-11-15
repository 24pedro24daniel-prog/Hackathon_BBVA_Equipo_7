"""CajaClara API. Arranque: uvicorn app.main:app --port 8000 --reload

Registra TODOS los routers desde el inicio (también los de Dev A): nadie vuelve a tocar este archivo.
"""
import logging

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.auth import verificar_api_key
from app.core.config import settings
from app.core.errors import registrar_handlers
from app.core.meta import iniciar_request
from app.routers import (
    alertas, analisis, asistente, fiados, forecast, health, ingesta,
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
app = FastAPI(title="CajaClara API", version=settings.API_VERSION, docs_url="/docs", redoc_url=None)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)
app.add_middleware(RequestIdMiddleware)

registrar_handlers(app)

# Público (monitoreo)
app.include_router(health.router, prefix=PREFIJO)

# Protegidos con X-API-Key
protegidos = [
    # Dev A
    webhooks.router, ingesta.router, media.router, impuestos.router, movimientos.router, asistente.router, salud.router,
    # Dev B
    resumen.router, forecast.router, fiados.router, pedidos.router, simulador.router,
    analisis.router, alertas.router,
    # Observabilidad interna
    llm_trazas.router,
]
for r in protegidos:
    app.include_router(r, prefix=PREFIJO, dependencies=[Depends(verificar_api_key)])

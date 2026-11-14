"""CajaClara API. Arranque: uvicorn app.main:app --port 8000 --reload

Registra TODOS los routers desde el inicio (también los de Dev A): nadie vuelve a tocar este archivo.
"""
from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.core.auth import verificar_api_key
from app.core.config import get_settings
from app.core.errors import registrar_errores
from app.core.meta import iniciar_peticion
from app.routers import (
    alertas, analisis, asistente, fiados, forecast, health, ingesta,
    impuestos, movimientos, pedidos, resumen, salud, simulador, webhooks,
)

settings = get_settings()
PREFIJO = "/api/v1"

app = FastAPI(title="CajaClara API", version=settings.VERSION_API, docs_url="/docs", redoc_url=None)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    rid = iniciar_peticion()
    response = await call_next(request)
    response.headers["X-Request-ID"] = rid
    return response


registrar_errores(app)

# Público (monitoreo)
app.include_router(health.router, prefix=PREFIJO)

# Protegidos con X-API-Key
protegidos = [
    # Dev A
    webhooks.router, ingesta.router, impuestos.router, movimientos.router, asistente.router, salud.router,
    # Dev B
    resumen.router, forecast.router, fiados.router, pedidos.router, simulador.router,
    analisis.router, alertas.router,
]
for r in protegidos:
    app.include_router(r, prefix=PREFIJO, dependencies=[Depends(verificar_api_key)])

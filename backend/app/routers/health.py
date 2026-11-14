"""Dueño: B. GET /health (contrato §9). Pública (sin X-API-Key) para los healthchecks.

Real para la BD (SELECT 1). Whisper/LLM vienen de `ingesta.estado_ia()` sin cargar modelos ni llamar a la red.
"""

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.services.ingesta import estado_ia

router = APIRouter(tags=["health"])


@router.get("/health")
def health(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        base_datos = "ok"
    except Exception:  # noqa: BLE001 - cualquier fallo de conexión cuenta como caído
        base_datos = "caido"
    ia = estado_ia()
    return {
        "estado": "ok" if base_datos == "ok" else "degradado",
        "version_api": settings.API_VERSION,
        "componentes": {
            "base_datos": base_datos,
            "whisper": ia["whisper"],
            "llm": ia["llm"],
            "forecast": {"estado": "mock", "modelo_version": None},
            "riesgo_atraso": {"estado": "mock", "modelo_version": None},
        },
    }

"""B12 — GET /health (público, sin API key). Whisper/LLM/VLM/R2 vienen de `ingesta.estado_ia()`
(sin cargar modelos ni llamar a la red)."""
from fastapi import APIRouter, Depends
from sqlalchemy import text

from app.core.config import settings
from app.core.deps import get_db
from app.services.ingesta import estado_ia

router = APIRouter(tags=["Operación"])


def _estado_bd(db) -> str:
    if db is None:
        return "sin_configurar"
    try:
        db.execute(text("select 1"))
        return "ok"
    except Exception:
        return "caido"


@router.get("/health")
def health(db=Depends(get_db)):
    bd = _estado_bd(db)
    ia = estado_ia()
    return {
        "estado": "ok" if bd in ("ok", "sin_configurar") else "degradado",
        "version_api": settings.API_VERSION,
        "componentes": {
            "base_datos": bd,
            "whisper": ia["whisper"],
            "llm": ia["llm"],
            "vlm": ia["vlm"],
            "almacenamiento": ia["r2"],
            "forecast": {"estado": "ok", "modelo_version": "0.3.1"},
            "riesgo_atraso": {"estado": "ok", "modelo_version": "0.2.0"},
        },
    }

"""B12 — GET /health (público, sin API key). FASE 0: componentes de IA fijos en 'ok'."""
from fastapi import APIRouter, Depends
from sqlalchemy import text

from app.core.config import settings
from app.core.deps import get_db

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
    return {
        "estado": "ok" if bd in ("ok", "sin_configurar") else "degradado",
        "version_api": settings.API_VERSION,
        "componentes": {
            "base_datos": bd,
            # TODO(B12): reemplazar por estado_ia() de Dev A (Whisper/LLM reales)
            "whisper": {"estado": "ok", "modelo": "faster-whisper-small"},
            "llm": {"estado": "ok", "modelo": "qwen2.5-7b-instruct",
                    "prompt_versions": {"extractor": "v3", "asistente": "v2", "cuaderno": "v1"}},
            "forecast": {"estado": "ok", "modelo_version": "0.3.1"},
            "riesgo_atraso": {"estado": "ok", "modelo_version": "0.2.0"},
        },
    }

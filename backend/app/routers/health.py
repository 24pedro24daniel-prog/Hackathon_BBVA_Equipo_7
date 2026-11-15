"""B12 — GET /health (público, sin API key). Whisper/LLM/VLM/R2 vienen de `ingesta.estado_ia()` y los modelos de B de
`finanzas.diagnostico_*` (sin cargar modelos ni llamar a la red: solo se lee metadata.json, cacheado)."""
from fastapi import APIRouter, Depends
from sqlalchemy import text

from app.core.config import settings
from app.core.deps import get_db
from app.services.finanzas import proyeccion as fc
from app.services.finanzas import riesgo
from app.services.finanzas.modelo_ml import diagnostico_forecast, diagnostico_riesgo_atraso
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


def _componente_modelo(diag: dict, modelo: str, version: str, ml: str) -> dict:
    """`estado = baseline`: responde con el baseline determinístico porque el modelo de ML no está disponible."""
    return {
        "estado": "ok" if diag["estado"] == "ok" else "baseline",
        "modelo": modelo,
        "modelo_version": version,
        "ml": {"tipo": ml, "estado": diag["estado"], "artefactos": diag.get("artefactos", False),
               "motivo": "; ".join(diag.get("motivos", [])) or None},
    }


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
            "forecast": _componente_modelo(diagnostico_forecast(), fc.MODELO, fc.VERSION, "lightgbm-quantile"),
            "riesgo_atraso": _componente_modelo(diagnostico_riesgo_atraso(), riesgo.MODELO, riesgo.VERSION, "clasificador"),
        },
    }

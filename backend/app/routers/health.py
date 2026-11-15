"""B12 — GET /health (público, sin API key). Whisper/LLM/VLM/R2 vienen de `ingesta.estado_ia()`; los modelos de ML de
`finanzas.modelo_ml.diagnostico_*`: la primera consulta carga los artefactos (una sola vez por proceso, quedan en caché y
el health comprueba de verdad que cargan); las siguientes no los vuelven a leer. Sin llamadas a la red."""
from fastapi import APIRouter, Depends
from sqlalchemy import text

from app.core.config import settings
from app.core.deps import get_db
from app.services.finanzas import proyeccion as fc
from app.services.finanzas import riesgo
from app.services.finanzas.modelo_ml import (
    MODELO_FORECAST,
    MODELO_SCORING,
    diagnostico_forecast,
    diagnostico_riesgo_atraso,
    diagnostico_scoring,
    motor_configurado,
)
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


def _ml(diag: dict, tipo: str) -> dict:
    return {"tipo": tipo, "estado": diag["estado"], "artefactos": diag.get("artefactos", False),
            "cargado": diag.get("cargado", False), "motivo": "; ".join(diag.get("motivos", [])) or None}  # fmt: skip


def _componente_modelo(diag: dict, modelo: str, version: str, ml: str) -> dict:
    """`estado = baseline`: responde con el baseline determinístico porque el modelo de ML no está disponible."""
    return {
        "estado": "ok" if diag["estado"] == "ok" else "baseline",
        "modelo": modelo,
        "modelo_version": version,
        "ml": _ml(diag, ml),
    }


def _componente_forecast() -> dict:
    diag = diagnostico_forecast()
    if diag["estado"] == "ok":
        componente = _componente_modelo(diag, MODELO_FORECAST, diag["modelo_version"], "lightgbm-quantile")
    else:
        componente = _componente_modelo(diag, fc.MODELO, fc.VERSION, "lightgbm-quantile")
    return {**componente, "motor_configurado": motor_configurado()}


def _componente_scoring() -> dict:
    """Credit scoring: sin modelo no hay baseline que lo reemplace; `score_crediticio` sale como no disponible."""
    diag = diagnostico_scoring()
    ok = diag["estado"] == "ok"
    return {"estado": "ok" if ok else "no_disponible", "modelo": MODELO_SCORING,
            "modelo_version": diag.get("modelo_version"), "ml": _ml(diag, "logreg")}  # fmt: skip


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
            "forecast": _componente_forecast(),
            "credit_scoring": _componente_scoring(),
            "riesgo_atraso": _componente_modelo(diagnostico_riesgo_atraso(), riesgo.MODELO, riesgo.VERSION, "clasificador"),
        },
    }

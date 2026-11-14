"""B3/B5 — Forecast F3 (baseline naive estacional + modelo ML si existe + fallback). FASE 0: mock."""
from datetime import date

from app.core.meta import construir_meta
from app.mocks import data as mock
from app.schemas.forecast import AjusteRequest, AjusteResponse, ForecastResponse


def forecast(db, empresa_id: str, horizonte_dias: int = 30, fecha_corte: date | None = None) -> ForecastResponse:
    base = mock.forecast_pedro()
    base["serie"] = base["serie"][:horizonte_dias]
    base["horizonte_dias"] = horizonte_dias
    return ForecastResponse.model_validate(
        {**base, "meta": construir_meta("forecast-lgbm-quantile", "0.3.1")}
    )


def crear_ajuste(db, empresa_id: str, ajuste: AjusteRequest) -> AjusteResponse:
    """B5. FASE 0: no persiste nada."""
    return AjusteResponse(ajuste_id="AJU-0003", forecast_recalculado=True)

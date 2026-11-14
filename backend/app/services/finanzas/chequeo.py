"""B8 — Chequeo antes de confirmar un pedido a crédito. FASE 0: mock que sí reacciona al monto."""
from datetime import date

from app.core.meta import construir_meta
from app.mocks import data as mock
from app.schemas.cuentas import ChequeoResponse


def chequeo_pedido(db, empresa_id: str, proveedor: str, monto, fecha_vencimiento: date) -> ChequeoResponse:
    return ChequeoResponse.model_validate(
        {**mock.chequeo_pedro(float(monto)), "meta": construir_meta("forecast-lgbm-quantile", "0.3.1")}
    )

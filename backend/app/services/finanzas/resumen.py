"""B2 — Resumen F2. FASE 0: mock."""
from datetime import date

from app.mocks import data as mock
from app.schemas.resumen import ResumenResponse


def resumen(db, empresa_id: str, periodo: str, fecha_corte: date | None = None) -> ResumenResponse:
    return ResumenResponse.model_validate(mock.resumen_pedro(periodo))

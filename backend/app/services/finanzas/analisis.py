"""B13 — Análisis F5. FASE 0: mock."""
from app.mocks import data as mock
from app.schemas.analisis import AnalisisResponse


def analisis(db, empresa_id: str, agrupar_por: str = "categoria", tipo: str = "egreso", **filtros) -> AnalisisResponse:
    return AnalisisResponse.model_validate(mock.analisis_pedro(agrupar_por, tipo))

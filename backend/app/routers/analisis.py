"""Dueño: B. GET /empresas/{empresa_id}/analisis (contrato §5). STUB Fase 0 (B13 lo reemplaza)."""

from datetime import date

from app import mock_contrato as mock
from app.routers._comun import EmpresaId, router_protegido
from app.schemas.analisis import AgruparPor, AnalisisResponse, CompararCon, TipoAnalisis

router = router_protegido("analisis")


@router.get("/empresas/{empresa_id}/analisis", response_model=AnalisisResponse)
def obtener_analisis(
    empresa_id: EmpresaId,
    desde: date | None = None,
    hasta: date | None = None,
    agrupar_por: AgruparPor = AgruparPor.categoria,
    tipo: TipoAnalisis = TipoAnalisis.egreso,
    comparar_con: CompararCon | None = None,
):
    return mock.analisis(agrupar_por.value, tipo.value)

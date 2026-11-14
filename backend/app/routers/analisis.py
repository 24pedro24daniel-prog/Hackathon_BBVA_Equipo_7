"""B13 — GET /empresas/{id}/analisis"""
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query

from app.core.deps import get_db
from app.schemas.analisis import AnalisisResponse
from app.services import finanzas

router = APIRouter(tags=["F5 Análisis"])


@router.get("/empresas/{empresa_id}/analisis", response_model=AnalisisResponse)
def obtener_analisis(
    empresa_id: str,
    desde: date | None = None,
    hasta: date | None = None,
    agrupar_por: Literal["categoria", "producto", "proveedor", "cliente_fiado", "metodo_pago", "mes"] = "categoria",
    tipo: Literal["ingreso", "egreso"] = "egreso",
    comparar_con: Literal["periodo_anterior", "mismo_periodo_anio_anterior"] | None = Query(None),
    db=Depends(get_db),
):
    return finanzas.analisis(db, empresa_id, agrupar_por, tipo, desde=desde, hasta=hasta, comparar_con=comparar_con)

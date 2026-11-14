"""B2 — GET /empresas/{id}/resumen"""
from fastapi import APIRouter, Depends, Query

from app.core.deps import get_db
from app.core.reloj import hoy
from app.schemas.resumen import ResumenResponse
from app.services import finanzas

router = APIRouter(tags=["F2 Resumen"])


@router.get("/empresas/{empresa_id}/resumen", response_model=ResumenResponse)
def obtener_resumen(empresa_id: str, periodo: str | None = Query(None, pattern=r"^\d{4}-\d{2}$"), db=Depends(get_db)):
    return finanzas.resumen(db, empresa_id, periodo or hoy().strftime("%Y-%m"))

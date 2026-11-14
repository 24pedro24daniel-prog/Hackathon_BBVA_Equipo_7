"""B3/B5 — GET /empresas/{id}/forecast · POST /empresas/{id}/forecast/ajustes"""
from fastapi import APIRouter, Depends, Query

from app.core.deps import get_db
from app.schemas.forecast import AjusteRequest, AjusteResponse, ForecastResponse
from app.services import finanzas

router = APIRouter(tags=["F3 Forecast"])


@router.get("/empresas/{empresa_id}/forecast", response_model=ForecastResponse)
def obtener_forecast(empresa_id: str, horizonte_dias: int = Query(30, ge=1, le=30), db=Depends(get_db)):
    return finanzas.forecast(db, empresa_id, horizonte_dias)


@router.post("/empresas/{empresa_id}/forecast/ajustes", response_model=AjusteResponse, status_code=201)
def crear_ajuste(empresa_id: str, body: AjusteRequest, db=Depends(get_db)):
    return finanzas.crear_ajuste(db, empresa_id, body)

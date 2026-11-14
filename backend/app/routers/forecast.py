"""Dueño: B. GET /empresas/{id}/forecast · POST /empresas/{id}/forecast/ajustes (contrato §4.1–4.2)."""

from fastapi import Depends, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.routers._comun import EmpresaId, router_protegido
from app.schemas.forecast import AjusteForecastRequest, AjusteForecastResponse, ForecastResponse
from app.services import finanzas

router = router_protegido("forecast")


@router.get("/empresas/{empresa_id}/forecast", response_model=ForecastResponse)
def obtener_forecast(
    empresa_id: EmpresaId, horizonte_dias: int = Query(30, ge=1, le=90), db: Session = Depends(get_db)
):
    return finanzas.forecast(db, empresa_id, horizonte_dias)


@router.post(
    "/empresas/{empresa_id}/forecast/ajustes", status_code=status.HTTP_201_CREATED, response_model=AjusteForecastResponse
)
def crear_ajuste(empresa_id: EmpresaId, body: AjusteForecastRequest):
    # STUB Fase 0 (B5 lo guarda en forecast_ajustes)
    return {"ajuste_id": "AJU-0003", "forecast_recalculado": True}

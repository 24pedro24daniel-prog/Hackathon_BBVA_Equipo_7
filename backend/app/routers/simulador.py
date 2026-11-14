"""B9 — POST /empresas/{id}/simular"""
from fastapi import APIRouter, Depends

from app.core.deps import get_db
from app.schemas.simulador import SimulacionRequest, SimulacionResponse
from app.services import finanzas

router = APIRouter(tags=["Simulador"])


@router.post("/empresas/{empresa_id}/simular", response_model=SimulacionResponse)
def simular(empresa_id: str, body: SimulacionRequest, db=Depends(get_db)):
    return finanzas.simular(db, empresa_id, body.acciones)

"""Dueño: B. POST /empresas/{empresa_id}/simular (contrato §4.6)."""

from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.routers._comun import EmpresaId, router_protegido
from app.schemas.simulador import SimulacionResponse, SimularRequest
from app.services import finanzas

router = router_protegido("simulador")


@router.post("/empresas/{empresa_id}/simular", response_model=SimulacionResponse)
def simular(empresa_id: EmpresaId, body: SimularRequest, db: Session = Depends(get_db)):
    return finanzas.simular(db, empresa_id, body.acciones)

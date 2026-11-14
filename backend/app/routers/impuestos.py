"""Dueño: A. POST /empresas/{empresa_id}/impuestos (contrato §1.5): registro por menú de botones."""

from fastapi import Depends, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.routers._comun import EmpresaId, router_protegido
from app.schemas.ingesta import ImpuestoRequest, ImpuestoResponse
from app.services.ingesta import impuestos

router = router_protegido("impuestos")


@router.post("/empresas/{empresa_id}/impuestos", status_code=status.HTTP_201_CREATED, response_model=ImpuestoResponse)
def registrar_impuesto(empresa_id: EmpresaId, body: ImpuestoRequest, db: Session = Depends(get_db)):
    return impuestos.registrar(db, empresa_id, body)

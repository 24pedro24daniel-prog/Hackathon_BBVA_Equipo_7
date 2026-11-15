"""Dueño: A. GET /empresas/{id}/salud · POST /empresas/{id}/metas (contrato §8)."""

from fastapi import Depends, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.routers._comun import EmpresaId, router_protegido
from app.schemas.salud import MetaRequest, MetaResponse, SaludResponse
from app.services.ingesta.servicio import empresa_o_404
from app.services.salud import credito, metas, score

router = router_protegido("salud")


@router.get("/empresas/{empresa_id}/salud", response_model=SaludResponse)
def obtener_salud(empresa_id: EmpresaId, db: Session = Depends(get_db)):
    empresa_o_404(db, empresa_id)
    return {**score.calcular_score(db, empresa_id), "score_crediticio": credito.score_crediticio(db, empresa_id)}


@router.post("/empresas/{empresa_id}/salud/recalcular", response_model=SaludResponse)
def recalcular_salud(empresa_id: EmpresaId, db: Session = Depends(get_db)):
    """Calcula el score del mes en curso y lo guarda en `score_salud` (el GET solo calcula, no escribe)."""
    empresa_o_404(db, empresa_id)
    return {**score.calcular_score(db, empresa_id, persistir=True),
            "score_crediticio": credito.score_crediticio(db, empresa_id)}


@router.post("/empresas/{empresa_id}/metas", status_code=status.HTTP_201_CREATED, response_model=MetaResponse)
def crear_meta(empresa_id: EmpresaId, body: MetaRequest, db: Session = Depends(get_db)):
    empresa_o_404(db, empresa_id)
    regla = body.regla.model_dump() if body.regla else None
    recordatorio = body.recordatorio.model_dump() if body.recordatorio else None
    return metas.crear_meta(db, empresa_id, body.plantilla, regla, recordatorio)

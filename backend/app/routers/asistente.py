"""Dueño: A. POST /empresas/{empresa_id}/asistente/mensajes (contrato §7)."""

from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.routers._comun import EmpresaId, router_protegido
from app.schemas.asistente import MensajeRequest, MensajeResponse
from app.services.asistente import orquestador
from app.services.ingesta.servicio import empresa_o_404

router = router_protegido("asistente")


@router.post("/empresas/{empresa_id}/asistente/mensajes", response_model=MensajeResponse)
def enviar_mensaje(empresa_id: EmpresaId, body: MensajeRequest, db: Session = Depends(get_db)):
    empresa_o_404(db, empresa_id)
    return orquestador.responder(db, empresa_id, body.mensaje, body.conversacion_id, body.canal)

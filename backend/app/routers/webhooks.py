"""Dueño: A. POST /webhooks/whatsapp (contrato §1.1). Uso interno del bot / chat simulado.

Enruta por empresa_id o telefono_hash: texto/audio → interpretar, imagen → cuaderno, botón → confirmar/corregir,
pregunta → asistente. Ver services/ingesta/whatsapp.py.
"""

from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.routers._comun import router_protegido
from app.schemas.ingesta import WebhookRequest, WebhookResponse
from app.services.ingesta import whatsapp

router = router_protegido("webhooks")


@router.post("/webhooks/whatsapp", response_model=WebhookResponse)
def webhook_whatsapp(body: WebhookRequest, db: Session = Depends(get_db)):
    return whatsapp.procesar(db, body)

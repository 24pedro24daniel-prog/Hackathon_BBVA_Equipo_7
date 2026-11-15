"""Dueño: A. POST /webhooks/whatsapp (contrato §1.1). Uso interno del bot / chat simulado.

Enruta por empresa_id o telefono_hash: texto/audio → interpretar, imagen → cuaderno, botón → confirmar/corregir,
pregunta → asistente. Ver services/ingesta/whatsapp.py.
"""

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.auth import Principal, autenticar, exigir_empresa
from app.db.session import get_db
from app.routers._comun import CON_LIMITE_IA, router_protegido
from app.schemas.ingesta import WebhookRequest, WebhookResponse
from app.services.ingesta import whatsapp

router = router_protegido("webhooks")


@router.post("/webhooks/whatsapp", response_model=WebhookResponse, dependencies=CON_LIMITE_IA)
def webhook_whatsapp(body: WebhookRequest, db: Session = Depends(get_db), principal: Principal = Depends(autenticar)):
    # Con Bearer y sin empresa_id en el body, la empresa sale del telefono_hash: tiene que ser la de la sesión.
    # (Un empresa_id en el body ya lo revisó el alcance por empresa.)
    if principal.es_sesion and not body.empresa_id:
        exigir_empresa(whatsapp.enrutar_empresa(db, body).empresa_id, "telefono_hash", principal)
    return whatsapp.procesar(db, body)

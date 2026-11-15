"""Dueño: A. POST /empresas/{empresa_id}/chat/mensajes (contrato §1.7): el chat de la app en un solo endpoint.

La decisión (registro / corrección / confirmación / asistente) la toma services/ingesta/enrutador.py, la misma lógica
que usa el webhook de WhatsApp.
"""

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.meta import construir_meta
from app.db import models as m
from app.db.session import get_db
from app.routers._comun import CON_LIMITE_IA, EmpresaId, router_protegido
from app.schemas.chat import ChatMensajeRequest, ChatMensajeResponse
from app.schemas.common import Canal
from app.schemas.ingesta import InterpretarRequest
from app.services.ingesta import enrutador, servicio

router = router_protegido("chat")


@router.post("/empresas/{empresa_id}/chat/mensajes", response_model=ChatMensajeResponse, dependencies=CON_LIMITE_IA,
             responses={422: {"description": "NO_INTERPRETABLE (audio no encontrado)"},
                        503: {"description": "SERVICIO_NO_DISPONIBLE (no se pudo escuchar el audio)"}})  # fmt: skip
def enviar(empresa_id: EmpresaId, body: ChatMensajeRequest, db: Session = Depends(get_db)):
    servicio.empresa_o_404(db, empresa_id)
    borrador = db.get(m.Borrador, body.borrador_id) if body.borrador_id else None
    canal = Canal.voz if body.canal == "voz" else Canal.texto
    transcrito = None
    texto = body.texto
    if canal == Canal.voz:
        transcrito = servicio.transcribir(InterpretarRequest(empresa_id=empresa_id, canal=canal, texto=body.texto,
                                                             media_url=body.media_url))  # fmt: skip
        texto = transcrito[0]
    r = enrutador.procesar_texto(db, empresa_id, texto, borrador, conversacion_id=body.conversacion_id,
                                 canal=canal, media_url=body.media_url, transcrito=transcrito)  # fmt: skip
    return {
        "tipo": r.tipo,
        "mensaje": r.mensaje,
        "transcripcion": r.transcripcion,
        "interpretacion": r.interpretacion,
        "confirmacion": r.confirmacion,
        "asistente": r.asistente,
        "conversacion_id": r.conversacion_id or body.conversacion_id,
        "meta": r.meta or construir_meta("reglas-chat", None).model_dump(mode="json"),
    }

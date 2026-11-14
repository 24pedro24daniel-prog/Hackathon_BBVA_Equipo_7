"""Dueño: A. POST /media/subidas: URL prefirmada para subir audios y fotos directo a Cloudflare R2 (contrato §1.0)."""

from datetime import datetime
from typing import Literal

from fastapi import Depends, status
from pydantic import Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.routers._comun import router_protegido
from app.schemas.common import ModeloContrato, ModeloEntrada
from app.services.ingesta import almacenamiento
from app.services.ingesta.servicio import empresa_o_404

router = router_protegido("media")


class SubidaRequest(ModeloEntrada):
    empresa_id: str
    tipo: Literal["audio", "imagen"]
    content_type: str = Field(min_length=1, max_length=100)
    tamano_bytes: int = Field(gt=0)


class SubidaResponse(ModeloContrato):
    media_url: str
    upload_url: str
    metodo: Literal["PUT"]
    headers_requeridos: dict[str, str]
    expira_en: datetime
    tamano_max_bytes: int


@router.post("/media/subidas", status_code=status.HTTP_201_CREATED, response_model=SubidaResponse,
             responses={503: {"description": "SERVICIO_NO_DISPONIBLE (R2 sin configurar)"}})  # fmt: skip
def pedir_subida(body: SubidaRequest, db: Session = Depends(get_db)):
    empresa_o_404(db, body.empresa_id)
    subida = almacenamiento.presignar_subida(body.empresa_id, body.tipo, body.content_type, body.tamano_bytes)
    return SubidaResponse(**subida.__dict__)

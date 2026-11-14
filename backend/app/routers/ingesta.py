"""Dueño: A. POST /ingesta/interpretar · /ingesta/confirmar · /ingesta/cuaderno (contrato §1.2–1.4)."""

from fastapi import Depends, Header, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.routers._comun import router_protegido
from app.schemas.ingesta import (
    ConfirmarRequest,
    ConfirmarResponse,
    CuadernoRequest,
    CuadernoResponse,
    InterpretarRequest,
    InterpretarResponse,
)
from app.services.ingesta import servicio

router = router_protegido("ingesta")


@router.post("/ingesta/interpretar", response_model=InterpretarResponse,
             responses={422: {"description": "NO_INTERPRETABLE"}, 503: {"description": "SERVICIO_NO_DISPONIBLE"}})  # fmt: skip
def interpretar(body: InterpretarRequest, db: Session = Depends(get_db)):
    return servicio.interpretar(db, body)


@router.post("/ingesta/confirmar", status_code=status.HTTP_201_CREATED, response_model=ConfirmarResponse,
             responses={204: {"description": "Borrador descartado"}, 409: {"description": "CONFLICTO"}})  # fmt: skip
def confirmar(
    body: ConfirmarRequest,
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    codigo, cuerpo = servicio.confirmar(db, body, idempotency_key)
    if codigo == status.HTTP_204_NO_CONTENT:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    return JSONResponse(status_code=codigo, content=ConfirmarResponse.model_validate(cuerpo).model_dump(mode="json"))


@router.post("/ingesta/cuaderno", response_model=CuadernoResponse)
def cuaderno(body: CuadernoRequest, db: Session = Depends(get_db)):
    return servicio.leer_cuaderno(db, body.empresa_id, body.media_url)

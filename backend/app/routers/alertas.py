"""Dueño: B. Alertas (contrato §6): GET /alertas · POST /alertas/{id}/accion · POST /alertas/evaluar ·
PUT /preferencias-alertas."""

from fastapi import Body, Depends, Path, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.routers._comun import EmpresaId, router_protegido
from app.schemas.alertas import (
    AccionAlertaRequest,
    AccionAlertaResponse,
    AlertasResponse,
    EvaluarAlertasRequest,
    PreferenciasAlertasRequest,
)
from app.schemas.common import EstadoAlerta
from app.services import alertas as motor

router = router_protegido("alertas")

_ESTADO_POR_ACCION = {"ejecutada": "atendida", "descartada": "descartada", "posponer": "activa"}


@router.get("/empresas/{empresa_id}/alertas", response_model=AlertasResponse)
def listar_alertas(
    empresa_id: EmpresaId, estado: EstadoAlerta = Query(EstadoAlerta.activa), db: Session = Depends(get_db)
):
    return motor.alertas(db, empresa_id, estado.value)


@router.post("/alertas/{alerta_id}/accion", response_model=AccionAlertaResponse)
def accion_alerta(body: AccionAlertaRequest, alerta_id: str = Path(pattern=r"^AL[RE]-\d{4,}$")):
    # STUB Fase 0 (B10 guarda accion_tomada y fecha_accion)
    return {"estado": _ESTADO_POR_ACCION[body.accion]}


@router.post("/empresas/{empresa_id}/alertas/evaluar", response_model=AlertasResponse)
def evaluar_alertas(
    empresa_id: EmpresaId,
    body: EvaluarAlertasRequest | None = Body(default=None),
    db: Session = Depends(get_db),
):
    body = body or EvaluarAlertasRequest()
    return {"items": motor.evaluar_alertas(db, empresa_id, body.disparador, body.entidad_id)}


@router.put("/empresas/{empresa_id}/preferencias-alertas", response_model=PreferenciasAlertasRequest)
def actualizar_preferencias(empresa_id: EmpresaId, body: PreferenciasAlertasRequest):
    # STUB Fase 0 (B11 lo guarda en preferencias_alertas)
    return body

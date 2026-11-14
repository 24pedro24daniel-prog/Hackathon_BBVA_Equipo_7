"""B10/B11 — alertas y preferencias."""
from fastapi import APIRouter, Body, Depends

from app.core.deps import get_db
from app.schemas.alertas import (
    AccionAlertaRequest, AccionAlertaResponse, AlertasResponse, PreferenciasAlertas,
)
from app.services import alertas as svc

router = APIRouter(tags=["F6 Alertas"])


@router.get("/empresas/{empresa_id}/alertas", response_model=AlertasResponse)
def listar_alertas(empresa_id: str, estado: str = "activa", db=Depends(get_db)):
    return svc.alertas(db, empresa_id, estado)


@router.post("/alertas/{alerta_id}/accion", response_model=AccionAlertaResponse)
def accionar(alerta_id: str, body: AccionAlertaRequest, db=Depends(get_db)):
    return svc.registrar_accion(db, alerta_id, body)


@router.post("/empresas/{empresa_id}/alertas/evaluar", response_model=AlertasResponse)
def evaluar(empresa_id: str, disparador: str | None = Body(None, embed=True),
            entidad_id: str | None = Body(None, embed=True), db=Depends(get_db)):
    """Interno: lo llama /ingesta/confirmar. Devuelve las alertas nuevas."""
    return AlertasResponse(items=svc.evaluar_alertas(db, empresa_id, disparador, entidad_id))


@router.put("/empresas/{empresa_id}/preferencias-alertas", response_model=PreferenciasAlertas)
def preferencias(empresa_id: str, body: PreferenciasAlertas, db=Depends(get_db)):
    return svc.guardar_preferencias(db, empresa_id, body)

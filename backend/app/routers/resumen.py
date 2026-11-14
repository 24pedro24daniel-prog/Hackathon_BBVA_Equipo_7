"""Dueño: B. GET /empresas/{empresa_id}/resumen (contrato §3). Llama a la interfaz de finanzas (mock en Fase 0)."""

from fastapi import Depends, Query
from sqlalchemy.orm import Session

from app.core.reloj import hoy
from app.db.session import get_db
from app.routers._comun import EmpresaId, router_protegido
from app.schemas.resumen import ResumenResponse
from app.services import finanzas

router = router_protegido("resumen")


@router.get("/empresas/{empresa_id}/resumen", response_model=ResumenResponse)
def obtener_resumen(
    empresa_id: EmpresaId,
    periodo: str | None = Query(None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    db: Session = Depends(get_db),
):
    return finanzas.resumen(db, empresa_id, periodo or hoy().strftime("%Y-%m"))

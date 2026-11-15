"""B6 — GET /empresas/{id}/fiados · POST /fiados/{fiado_id}/recordatorio"""
from fastapi import APIRouter, Depends

from app.core.deps import get_db
from app.schemas.common import EstadoCuenta
from app.schemas.cuentas import FiadosResponse, RecordatorioResponse
from app.services import finanzas

router = APIRouter(tags=["F4 Cuentas"])


@router.get("/empresas/{empresa_id}/fiados", response_model=FiadosResponse)
def listar_fiados(empresa_id: str, estado: EstadoCuenta = EstadoCuenta.pendiente, db=Depends(get_db)):
    return finanzas.fiados(db, empresa_id, estado.value)


@router.post("/fiados/{fiado_id}/recordatorio", response_model=RecordatorioResponse)
def recordatorio(fiado_id: str, db=Depends(get_db)):
    """Genera el texto del recordatorio (no lo envía al vecino)."""
    return finanzas.recordatorio(db, fiado_id)

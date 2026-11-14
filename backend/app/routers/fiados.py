"""Dueño: B. GET /empresas/{id}/fiados · POST /fiados/{fiado_id}/recordatorio (contrato §4.3)."""

from fastapi import Depends, Path, Query
from sqlalchemy.orm import Session

from app import mock_contrato as mock
from app.core.errors import NoEncontrado
from app.db.session import get_db
from app.routers._comun import EmpresaId, router_protegido
from app.schemas.common import EstadoCuenta
from app.schemas.cuentas import FiadosResponse, RecordatorioResponse
from app.services import finanzas

router = router_protegido("fiados")


@router.get("/empresas/{empresa_id}/fiados", response_model=FiadosResponse)
def listar_fiados(
    empresa_id: EmpresaId, estado: EstadoCuenta = Query(EstadoCuenta.pendiente), db: Session = Depends(get_db)
):
    return finanzas.fiados(db, empresa_id, estado.value)


@router.post("/fiados/{fiado_id}/recordatorio", response_model=RecordatorioResponse)
def recordatorio(fiado_id: str = Path(pattern=r"^FIA-\d{4,}$")):
    # STUB Fase 0 (B6: plantilla con los datos reales del fiado)
    respuesta = mock.recordatorio(fiado_id)
    if respuesta is None:
        raise NoEncontrado("No encontré ese fiado.")
    return respuesta

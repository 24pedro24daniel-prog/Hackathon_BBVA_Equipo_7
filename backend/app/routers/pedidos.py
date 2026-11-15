"""B7/B8 — GET /empresas/{id}/pedidos · POST /empresas/{id}/pedidos/chequeo · POST /empresas/{id}/cuentas/anular"""
from fastapi import APIRouter, Depends

from app.core.deps import get_db
from app.schemas.common import EstadoCuenta
from app.routers._comun import EmpresaId
from app.schemas.cuentas import (
    AnularCuentaRequest,
    AnularCuentaResponse,
    ChequeoRequest,
    ChequeoResponse,
    PedidosResponse,
)
from app.services import finanzas
from app.services.finanzas.anulacion import anular_cuenta

router = APIRouter(tags=["F4 Cuentas"])


@router.get("/empresas/{empresa_id}/pedidos", response_model=PedidosResponse)
def listar_pedidos(empresa_id: str, estado: EstadoCuenta = EstadoCuenta.pendiente, db=Depends(get_db)):
    return finanzas.pedidos(db, empresa_id, estado.value)


@router.post("/empresas/{empresa_id}/pedidos/chequeo", response_model=ChequeoResponse)
def chequear_pedido(empresa_id: str, body: ChequeoRequest, db=Depends(get_db)):
    return finanzas.chequeo_pedido(db, empresa_id, body.proveedor, body.monto, body.fecha_vencimiento)


@router.post("/empresas/{empresa_id}/cuentas/anular", response_model=AnularCuentaResponse)
def anular(empresa_id: EmpresaId, body: AnularCuentaRequest, db=Depends(get_db)):
    """Anula un fiado, pedido o impuesto registrado por error (no se borra: deja de contar en todo)."""
    return anular_cuenta(db, empresa_id, body.tipo, body.id)

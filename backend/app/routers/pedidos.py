"""B7/B8 — GET /empresas/{id}/pedidos · POST /empresas/{id}/pedidos/chequeo"""
from fastapi import APIRouter, Depends

from app.core.deps import get_db
from app.schemas.common import EstadoCuenta
from app.schemas.cuentas import ChequeoRequest, ChequeoResponse, PedidosResponse
from app.services import finanzas

router = APIRouter(tags=["F4 Cuentas"])


@router.get("/empresas/{empresa_id}/pedidos", response_model=PedidosResponse)
def listar_pedidos(empresa_id: str, estado: EstadoCuenta = EstadoCuenta.pendiente, db=Depends(get_db)):
    return finanzas.pedidos(db, empresa_id, estado.value)


@router.post("/empresas/{empresa_id}/pedidos/chequeo", response_model=ChequeoResponse)
def chequear_pedido(empresa_id: str, body: ChequeoRequest, db=Depends(get_db)):
    return finanzas.chequeo_pedido(db, empresa_id, body.proveedor, body.monto, body.fecha_vencimiento)

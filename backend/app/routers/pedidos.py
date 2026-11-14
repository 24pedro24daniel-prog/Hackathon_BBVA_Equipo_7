"""Dueño: B. GET /empresas/{id}/pedidos · POST /empresas/{id}/pedidos/chequeo (contrato §4.4–4.5)."""

from fastapi import Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.routers._comun import EmpresaId, router_protegido
from app.schemas.common import EstadoCuenta
from app.schemas.cuentas import ChequeoRequest, ChequeoResponse, PedidosResponse
from app.services import finanzas

router = router_protegido("pedidos")


@router.get("/empresas/{empresa_id}/pedidos", response_model=PedidosResponse)
def listar_pedidos(
    empresa_id: EmpresaId, estado: EstadoCuenta = Query(EstadoCuenta.pendiente), db: Session = Depends(get_db)
):
    return finanzas.pedidos(db, empresa_id, estado.value)


@router.post("/empresas/{empresa_id}/pedidos/chequeo", response_model=ChequeoResponse)
def chequeo_pedido(empresa_id: EmpresaId, body: ChequeoRequest, db: Session = Depends(get_db)):
    return finanzas.chequeo_pedido(db, empresa_id, body.proveedor, body.monto, body.fecha_vencimiento)

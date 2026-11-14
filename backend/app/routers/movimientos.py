"""Dueño: A. GET/POST /empresas/{empresa_id}/movimientos (contrato §2)."""

from datetime import date

from fastapi import Depends, Header, status
from sqlalchemy.orm import Session

from app.core.paginacion import Pagina, parametros_pagina
from app.db.session import get_db
from app.routers._comun import EmpresaId, router_protegido
from app.schemas.common import Canal, TipoMovimiento
from app.schemas.ingesta import ConfirmarResponse
from app.schemas.movimientos import MovimientoManualRequest, MovimientosResponse
from app.services.ingesta import movimientos as consulta
from app.services.ingesta import servicio

router = router_protegido("movimientos")


@router.get("/empresas/{empresa_id}/movimientos", response_model=MovimientosResponse)
def listar_movimientos(
    empresa_id: EmpresaId,
    desde: date | None = None,
    hasta: date | None = None,
    tipo: TipoMovimiento | None = None,
    categoria: str | None = None,
    canal: Canal | None = None,
    pagina: Pagina = Depends(parametros_pagina),
    db: Session = Depends(get_db),
):
    servicio.empresa_o_404(db, empresa_id)
    return consulta.listar(db, empresa_id, pagina, desde=desde, hasta=hasta, tipo=tipo.value if tipo else None,
                           categoria=categoria, canal=canal.value if canal else None)  # fmt: skip


@router.post("/empresas/{empresa_id}/movimientos", status_code=status.HTTP_201_CREATED, response_model=ConfirmarResponse)
def crear_movimiento(
    empresa_id: EmpresaId,
    body: MovimientoManualRequest,
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    return servicio.registrar_manual(db, empresa_id, body, idempotency_key)

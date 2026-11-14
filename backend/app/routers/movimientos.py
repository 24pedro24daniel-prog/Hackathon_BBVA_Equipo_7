"""STUB (Dueño: Dev A) — GET/POST /empresas/{id}/movimientos."""
from typing import Any

from fastapi import APIRouter, Body, Depends

from app.core.deps import get_db
from app.mocks import data as mock
from app.services import finanzas

router = APIRouter(tags=["Movimientos"])


@router.get("/empresas/{empresa_id}/movimientos")
def listar_movimientos(empresa_id: str):
    return {"items": [], "next_cursor": None}


@router.post("/empresas/{empresa_id}/movimientos", status_code=201)
def crear_movimiento(empresa_id: str, body: dict[str, Any] = Body(...), db=Depends(get_db)):
    mov_id = mock.siguiente_movimiento()
    return {"movimiento_id": mov_id, "registros_creados": [{"tabla": "transacciones", "id": mov_id}],
            "alertas_disparadas": [], "saldo_caja_negocio": float(finanzas.saldo_caja(db, empresa_id))}

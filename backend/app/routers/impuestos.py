"""STUB (Dueño: Dev A) — POST /empresas/{id}/impuestos."""
from typing import Any

from fastapi import APIRouter, Body

router = APIRouter(tags=["F1 Ingesta"])


@router.post("/empresas/{empresa_id}/impuestos", status_code=201)
def registrar_impuesto(empresa_id: str, body: dict[str, Any] = Body(...)):
    return {"impuesto_id": "IMP-0009", "estado": "al_dia", "proximo_vencimiento": "2026-12-15"}

"""STUB (Dueño: Dev A) — POST /empresas/{id}/asistente/mensajes."""
from typing import Any

from fastapi import APIRouter, Body

from app.mocks import stubs_a

router = APIRouter(tags=["F7 Asistente"])


@router.post("/empresas/{empresa_id}/asistente/mensajes")
def mensaje(empresa_id: str, body: dict[str, Any] = Body(...)):
    return stubs_a.asistente(body.get("mensaje", ""), body.get("conversacion_id"))

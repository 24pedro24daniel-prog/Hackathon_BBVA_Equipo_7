"""STUB (Dueño: Dev A) — GET /empresas/{id}/salud · POST /empresas/{id}/metas."""
from typing import Any

from fastapi import APIRouter, Body

from app.core.meta import construir_meta
from app.mocks import data as mock

router = APIRouter(tags=["F8 Salud"])


@router.get("/empresas/{empresa_id}/salud")
def obtener_salud(empresa_id: str):
    return {**mock.salud_pedro(), "meta": construir_meta("score-reglas", "0.1.0").model_dump(mode="json")}


@router.post("/empresas/{empresa_id}/metas", status_code=201)
def crear_meta(empresa_id: str, body: dict[str, Any] = Body(...)):
    return {"meta_id": "MET-0005", "estado": "activa"}

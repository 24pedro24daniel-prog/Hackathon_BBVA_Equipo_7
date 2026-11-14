"""STUB (Dueño: Dev A) — /ingesta/interpretar · /confirmar · /cuaderno.

El flujo de confirmar ya muestra el cruce real A→B (PLAN §4.3): registrar -> alertas.evaluar -> saldo_caja.
"""
from typing import Any

from fastapi import APIRouter, Body, Depends, Response

from app.core.deps import get_db
from app.core.errors import ApiError, Codigo
from app.mocks import data as mock
from app.mocks import stubs_a
from app.services import alertas as svc_alertas
from app.services.alertas.motor import DISPARADOR_COMPRA_CREDITO
from app.services import finanzas

router = APIRouter(tags=["F1 Ingesta"])


@router.post("/ingesta/interpretar")
def interpretar(body: dict[str, Any] = Body(...)):
    res = stubs_a.interpretar_respuesta(body.get("canal", "texto"), body.get("texto"))
    if res is None:
        raise ApiError(Codigo.NO_INTERPRETABLE,
                       'No entendí bien. ¿Me lo dices de otra forma? Por ejemplo: "vendí 2 cervezas".')
    return res


@router.post("/ingesta/confirmar", status_code=201)
def confirmar(body: dict[str, Any] = Body(...), db=Depends(get_db)):
    mov = mock.BORRADORES.get(body.get("borrador_id"))
    if mov is None:
        raise ApiError(Codigo.NO_ENCONTRADO, "Ese registro ya no existe. Vuelve a enviarlo.")
    correcciones = body.get("correcciones") or {}
    if body.get("confirmado") is False and not correcciones:
        mock.BORRADORES.pop(body["borrador_id"], None)
        return Response(status_code=204)
    final = {**mov, **correcciones}
    mock.BORRADORES.pop(body["borrador_id"], None)
    stubs_a.aplicar_al_saldo(final)                                   # A: registrador.registrar_movimiento(...)
    disparador = DISPARADOR_COMPRA_CREDITO if final.get("tipo") == "compra" else None
    nuevas = svc_alertas.evaluar_alertas(db, "EMP-0001", disparador)  # B
    mov_id = mock.siguiente_movimiento()
    return {
        "movimiento_id": mov_id,
        "registros_creados": [{"tabla": "deudas" if final.get("tipo") == "compra" else "transacciones", "id": mov_id}],
        "alertas_disparadas": [a.model_dump(mode="json") for a in nuevas],
        "saldo_caja_negocio": float(finanzas.saldo_caja(db, "EMP-0001")),  # B
    }


@router.post("/ingesta/cuaderno")
def cuaderno(body: dict[str, Any] = Body(default={})):
    return stubs_a.cuaderno()

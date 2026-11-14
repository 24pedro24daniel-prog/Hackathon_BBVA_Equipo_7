"""B6 — GET /empresas/{id}/fiados · POST /fiados/{fiado_id}/recordatorio"""
from fastapi import APIRouter, Depends

from app.core.deps import get_db
from app.core.errors import NoEncontrado
from app.schemas.common import EstadoCuenta
from app.schemas.cuentas import FiadosResponse, RecordatorioResponse
from app.services import finanzas

router = APIRouter(tags=["F4 Cuentas"])


@router.get("/empresas/{empresa_id}/fiados", response_model=FiadosResponse)
def listar_fiados(empresa_id: str, estado: EstadoCuenta = EstadoCuenta.pendiente, db=Depends(get_db)):
    return finanzas.fiados(db, empresa_id, estado.value)


@router.post("/fiados/{fiado_id}/recordatorio", response_model=RecordatorioResponse)
def recordatorio(fiado_id: str, db=Depends(get_db)):
    # FASE 0: busca en el mock. B6 real: leer cuaderno_fiado + plantilla de recordatorio.
    items = finanzas.fiados(db, "EMP-0001").items
    f = next((x for x in items if x.fiado_id == fiado_id), None)
    if f is None:
        raise NoEncontrado("No encontré ese fiado.")
    return RecordatorioResponse(
        mensaje=f"Hola, {f.cliente} 😊 Le recuerdo amablemente los S/ {float(f.monto):g} pendientes en la bodega. ¡Gracias!"
    )

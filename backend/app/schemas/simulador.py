"""Simulador de escenarios (contract.md §4.6). Dueño: B."""
from datetime import date

from pydantic import BaseModel, Field

from app.schemas.common import Confianza, Dinero, EstadoCaja, Meta, TipoAccionSimulador


class Accion(BaseModel):
    tipo: TipoAccionSimulador
    pedido_id: str | None = None
    nuevo_monto: Dinero | None = None   # reducir_pedido
    partes: int | None = Field(default=None, ge=2)  # pagar_en_partes
    fechas: list[date] | None = None    # pagar_en_partes / diferir_pago
    fiado_ids: list[str] | None = None  # cobrar_fiados
    fecha: date | None = None           # cobrar_fiados / diferir_pago
    monto: Dinero | None = None         # limitar_retiros / ajustar_gasto


class SimulacionRequest(BaseModel):
    acciones: list[Accion] = Field(min_length=1)


class ResultadoSaldo(BaseModel):
    saldo_minimo: Dinero
    fecha: date
    estado_caja: EstadoCaja


class PuntoSimulado(BaseModel):
    fecha: date
    p50: Dinero


class SimulacionResponse(BaseModel):
    sin_acciones: ResultadoSaldo
    con_acciones: ResultadoSaldo
    mejora: Dinero
    serie_con_acciones: list[PuntoSimulado]
    fundamento: str | None = None   # EXT
    limites: str | None = None      # EXT
    confianza: Confianza | None = None  # EXT
    ventana_hasta: date | None = None   # EXT: último día que entra a la comparación del saldo mínimo
    notas: list[str] = []               # EXT: pagos/cobros simulados que quedaron fuera del horizonte
    meta: Meta

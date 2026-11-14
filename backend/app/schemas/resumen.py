"""F2 — Resumen financiero (contract.md §3). Dueño: B."""
from datetime import date

from pydantic import BaseModel

from app.schemas.common import Dinero


class IndSaldo(BaseModel):
    valor: Dinero
    variacion_pct: float | None = None


class IndGanancia(IndSaldo):
    es_aproximada: bool = False
    rango: list[Dinero] | None = None  # [min, max] cuando faltan costos


class IndRetiros(BaseModel):
    valor: Dinero
    sueldo_fijo_definido: Dinero | None = None
    promedio_historico: Dinero | None = None


class IndPendienteCobro(BaseModel):
    valor: Dinero
    n_fiados: int


class IndPagosPendientes(BaseModel):
    valor: Dinero
    n_obligaciones: int
    detalle: str | None = None  # EXT del front


class Indicadores(BaseModel):
    saldo_caja_negocio: IndSaldo
    ingresos_mes: IndSaldo
    egresos_mes: IndSaldo
    ganancia_neta: IndGanancia
    retiros_personales: IndRetiros
    pendiente_cobro: IndPendienteCobro
    pagos_pendientes: IndPagosPendientes


class ResumenResponse(BaseModel):
    empresa_id: str
    periodo: str
    corte: date
    dias_con_datos: int | None = None            # EXT: estado "día 3"
    dias_requeridos_forecast: int | None = None  # EXT
    indicadores: Indicadores
    variacion_vs: str | None = None

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
    sueldo_frecuencia: str | None = None     # EXT: frecuencia del sueldo fijo (semanal, mensual…)
    exceso_vs_promedio: Dinero | None = None  # EXT: valor − promedio_historico (si es positivo)
    sueldo_esperado_a_la_fecha: Dinero | None = None  # EXT: lo que te tocaba sacar este mes hasta hoy (según tu sueldo fijo)
    exceso_vs_sueldo: Dinero | None = None   # EXT: valor − sueldo_esperado_a_la_fecha (si es positivo)


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


class Negocio(BaseModel):
    nombre: str


class ResumenResponse(BaseModel):
    empresa_id: str
    negocio: Negocio | None = None               # EXT: nombre del negocio (empresas.nombre_ficticio)
    periodo: str
    corte: date
    dias_con_datos: int | None = None            # EXT: estado "día 3"
    dias_requeridos_forecast: int | None = None  # EXT
    indicadores: Indicadores
    variacion_vs: str | None = None

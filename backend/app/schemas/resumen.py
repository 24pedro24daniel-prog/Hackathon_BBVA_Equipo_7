"""F2 — Resumen financiero (contrato §3)."""

from datetime import date

from app.schemas.common import Dinero, ModeloContrato


class Indicador(ModeloContrato):
    valor: Dinero
    variacion_pct: float | None = None


class IndicadorGanancia(Indicador):
    es_aproximada: bool = False
    rango: list[Dinero] | None = None


class IndicadorRetiros(ModeloContrato):
    valor: Dinero
    sueldo_fijo_definido: Dinero | None = None
    promedio_historico: Dinero | None = None


class IndicadorCobro(ModeloContrato):
    valor: Dinero
    n_fiados: int


class IndicadorPagos(ModeloContrato):
    valor: Dinero
    n_obligaciones: int


class Indicadores(ModeloContrato):
    saldo_caja_negocio: Indicador
    ingresos_mes: Indicador
    egresos_mes: Indicador
    ganancia_neta: IndicadorGanancia
    retiros_personales: IndicadorRetiros
    pendiente_cobro: IndicadorCobro
    pagos_pendientes: IndicadorPagos


class ResumenResponse(ModeloContrato):
    empresa_id: str
    periodo: str
    corte: date
    indicadores: Indicadores
    variacion_vs: str | None = None

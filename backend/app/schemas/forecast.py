"""F3 — Forecast y "disponible para gastar" (contrato §4.1–4.2)."""

from datetime import date

from pydantic import Field

from app.schemas.common import Dinero, Meta, ModeloContrato, ModeloEntrada, Probabilidad


class PuntoSerie(ModeloContrato):
    fecha: date
    ingresos_esperados: Dinero
    egresos_esperados: Dinero
    p10: Dinero
    p50: Dinero
    p90: Dinero


class ObligacionAsociada(ModeloContrato):
    tipo: str
    id: str
    proveedor: str | None = None
    monto: Dinero


class DiaCritico(ModeloContrato):
    fecha: date
    saldo_p50: Dinero
    probabilidad_deficit: Probabilidad
    obligacion_asociada: ObligacionAsociada | None = None


class ComponentesDisponible(ModeloContrato):
    saldo_actual: Dinero
    cobros_esperados: Dinero
    pagos_comprometidos: Dinero
    minimo_operativo: Dinero
    reserva_impuestos: Dinero


class DisponibleParaGastar(ModeloContrato):
    valor: Dinero
    formula: str
    componentes: ComponentesDisponible
    mensaje: str


class Baseline(ModeloContrato):
    nombre: str
    mae_backtest: float | None = None


class ForecastResponse(ModeloContrato):
    empresa_id: str
    fecha_corte: date
    horizonte_dias: int
    saldo_actual: Dinero
    minimo_operativo: Dinero | None = None
    serie: list[PuntoSerie]
    dia_critico: DiaCritico | None = None
    disponible_para_gastar: DisponibleParaGastar | None = None
    ajustes_manuales_aplicados: list[dict] = []
    baseline: Baseline | None = None
    modelo_metricas: dict | None = None
    meta: Meta


class AjusteForecastRequest(ModeloEntrada):
    fecha: date
    concepto: str = Field(min_length=1, max_length=100)
    monto: Dinero = Field(ge=0)
    motivo: str | None = Field(default=None, max_length=255)


class AjusteForecastResponse(ModeloContrato):
    ajuste_id: str
    forecast_recalculado: bool

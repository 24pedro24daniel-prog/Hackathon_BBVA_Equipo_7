"""F3 — Forecast y ajustes (contract.md §4.1–4.2). Dueño: B."""
from datetime import date

from pydantic import BaseModel, Field

from app.schemas.common import Confianza, Dinero, Meta


class PuntoSerie(BaseModel):
    fecha: date
    ingresos_esperados: Dinero
    egresos_esperados: Dinero
    p10: Dinero
    p50: Dinero
    p90: Dinero


class ObligacionAsociada(BaseModel):
    tipo: str
    id: str
    proveedor: str | None = None
    monto: Dinero


class DiaCritico(BaseModel):
    fecha: date
    saldo_p50: Dinero
    probabilidad_deficit: float
    obligacion_asociada: ObligacionAsociada | None = None


class ComponentesDisponible(BaseModel):
    saldo_actual: Dinero
    cobros_esperados: Dinero
    pagos_comprometidos: Dinero
    minimo_operativo: Dinero
    reserva_impuestos: Dinero


class DisponibleParaGastar(BaseModel):
    valor: Dinero
    formula: str
    componentes: ComponentesDisponible
    mensaje: str


class ProximoEvento(BaseModel):  # EXT: lista "Lo que viene"
    fecha: date
    concepto: str
    monto: Dinero
    tipo: str
    ponderado: bool | None = None
    ref_id: str | None = None


class Baseline(BaseModel):
    nombre: str
    mae_backtest: float | None = None


class ModeloMetricas(BaseModel):
    mae_backtest: float | None = None
    cobertura_p10_p90: float | None = None


class ForecastResponse(BaseModel):
    empresa_id: str
    fecha_corte: date
    horizonte_dias: int
    saldo_actual: Dinero
    minimo_operativo: Dinero | None = None
    serie: list[PuntoSerie] = []
    dia_critico: DiaCritico | None = None
    disponible_para_gastar: DisponibleParaGastar | None = None
    proximos_eventos: list[ProximoEvento] = []     # EXT
    ajustes_manuales_aplicados: list[dict] = []
    baseline: Baseline | None = None
    modelo_metricas: ModeloMetricas | None = None
    fundamento: str | None = None                  # EXT
    limites: str | None = None                     # EXT
    confianza: Confianza | None = None             # EXT
    # EXT: usuario nuevo sin datos suficientes
    disponible: bool | None = None
    dias_con_datos: int | None = None
    dias_requeridos: int | None = None
    meta: Meta


class AjusteRequest(BaseModel):
    fecha: date
    concepto: str = Field(min_length=1)
    monto: Dinero
    motivo: str | None = None


class AjusteResponse(BaseModel):
    ajuste_id: str
    forecast_recalculado: bool

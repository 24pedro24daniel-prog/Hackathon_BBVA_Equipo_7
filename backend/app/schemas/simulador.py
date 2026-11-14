"""Simulador de escenarios (contrato §4.6)."""

from datetime import date

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import Dinero, EstadoCaja, Meta, ModeloContrato, TipoAccionSimulador


class Accion(BaseModel):
    """Una acción del simulador. Los campos dependen del tipo; se aceptan extras por tipo."""

    model_config = ConfigDict(extra="allow", use_enum_values=True)

    tipo: TipoAccionSimulador
    pedido_id: str | None = None
    nuevo_monto: Dinero | None = Field(default=None, ge=0)
    partes: int | None = Field(default=None, ge=2, le=12)
    fechas: list[date] | None = None
    fiado_ids: list[str] | None = None
    fecha: date | None = None
    monto: Dinero | None = None


class SimularRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    acciones: list[Accion] = Field(min_length=1)


class ResultadoEscenario(ModeloContrato):
    saldo_minimo: Dinero
    fecha: date
    estado_caja: EstadoCaja


class PuntoSimulado(ModeloContrato):
    fecha: date
    p50: Dinero


class SimulacionResponse(ModeloContrato):
    sin_acciones: ResultadoEscenario
    con_acciones: ResultadoEscenario
    mejora: Dinero
    serie_con_acciones: list[PuntoSimulado]
    meta: Meta

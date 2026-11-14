"""F6 — Alertas y nudges (contrato §6)."""

from datetime import date, datetime

from pydantic import Field

from app.schemas.common import (
    AccionAlerta,
    CanalNotificacion,
    Dinero,
    EstadoAlerta,
    Meta,
    ModeloContrato,
    ModeloEntrada,
    NivelRiesgo,
    TipoAlerta,
)


class Causa(ModeloContrato):
    descripcion: str
    monto: Dinero


class AccionBoton(ModeloContrato):
    tipo: str
    texto_boton: str
    payload: dict = {}


class Alerta(ModeloContrato):
    alerta_id: str
    tipo: TipoAlerta
    prioridad: int = Field(ge=1, le=8)
    creada_en: datetime
    fecha_evento: date
    monto: Dinero | None = None
    probabilidad: float | None = None
    nivel_riesgo: NivelRiesgo | None = None
    titulo: str
    insight: str
    causas: list[Causa] = []
    accion: AccionBoton | None = None
    microexplicacion: str | None = None
    canales: list[CanalNotificacion] = []
    estado: EstadoAlerta
    meta: Meta | None = None


class AlertasResponse(ModeloContrato):
    items: list[Alerta]


class AccionAlertaRequest(ModeloEntrada):
    accion: AccionAlerta
    detalle: str | None = Field(default=None, max_length=255)


class AccionAlertaResponse(ModeloContrato):
    estado: EstadoAlerta


class EvaluarAlertasRequest(ModeloEntrada):
    disparador: str | None = None
    entidad_id: str | None = None


class PreferenciasAlertasRequest(ModeloEntrada):
    canales: list[CanalNotificacion] = Field(min_length=1)
    max_por_dia: int = Field(default=2, ge=0, le=10)
    silencio_desde: str = Field(default="21:00", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    silencio_hasta: str = Field(default="07:00", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    resumen_semanal: bool = True

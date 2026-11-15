"""F6 — Alertas y preferencias (contract.md §6). Dueño: B."""
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import Dinero, Meta, NivelRiesgo, TipoAlerta


class Causa(BaseModel):
    descripcion: str
    monto: Dinero


class AccionAlertaSugerida(BaseModel):
    tipo: str
    texto_boton: str
    payload: dict = {}


class Alerta(BaseModel):
    alerta_id: str
    tipo: TipoAlerta
    prioridad: int = Field(ge=1, le=8)
    creada_en: datetime
    fecha_evento: date | None = None
    dias_para_evento: int | None = None   # EXT
    monto: Dinero | None = None
    probabilidad: float | None = None
    nivel_riesgo: NivelRiesgo | None = None
    titulo: str
    titulo_corto: str | None = None       # EXT (chat)
    insight: str
    resumen_causas: str | None = None     # EXT
    causas: list[Causa] = []
    accion: AccionAlertaSugerida | None = None
    microexplicacion: str | None = None
    canales: list[str] = ["app"]
    estado: str = "activa"
    enviada_en: datetime | None = None    # null = guardada por horario silencioso
    persistida: bool = True               # EXT: false = vigente pero aún sin guardar (alerta_id `ALR-PEND.…`, estable)
    meta: Meta | None = None


class AlertasResponse(BaseModel):
    items: list[Alerta]


class AccionAlertaRequest(BaseModel):
    accion: Literal["ejecutada", "descartada", "posponer"]
    detalle: str | None = None


class AccionAlertaResponse(BaseModel):
    estado: str  # atendida | descartada | pospuesta
    alerta_id: str | None = None  # EXT: id definitivo (si la alerta estaba pendiente de guardar, ya quedó guardada)


class PreferenciasAlertas(BaseModel):
    canales: list[str] = ["whatsapp"]
    max_por_dia: int = Field(default=2, ge=0, le=10)
    silencio_desde: str = Field(default="21:00", pattern=r"^\d{2}:\d{2}$")
    silencio_hasta: str = Field(default="07:00", pattern=r"^\d{2}:\d{2}$")
    resumen_semanal: bool = True

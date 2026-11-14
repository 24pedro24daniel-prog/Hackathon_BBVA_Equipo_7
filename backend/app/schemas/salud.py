"""F8 — Plan de salud, score y metas (contrato §8)."""

from pydantic import Field

from app.schemas.common import EstadoMeta, Frecuencia, Meta, ModeloContrato, ModeloEntrada, PlantillaMeta, TipoRegla


class Subindicador(ModeloContrato):
    id: str
    nombre: str
    valor: int = Field(ge=0, le=100)
    detalle: str
    peso: float = Field(ge=0, le=1)


class PuntoHistorial(ModeloContrato):
    mes: str
    score: int


class Racha(ModeloContrato):
    tipo: str
    valor: int


class SaludResponse(ModeloContrato):
    score: int = Field(ge=0, le=100)
    score_anterior: int | None = None
    etapa_actual: str
    subindicadores: list[Subindicador]
    historial: list[PuntoHistorial] = []
    rachas: list[Racha] = []
    consentimiento_compartir_historial: bool = False
    meta: Meta


class ReglaMetaEntrada(ModeloEntrada):
    tipo: TipoRegla
    valor: float = Field(gt=0)
    destino: str | None = Field(default=None, max_length=30)


class RecordatorioEntrada(ModeloEntrada):
    frecuencia: Frecuencia
    dia: str | int | None = None


class MetaRequest(ModeloEntrada):
    plantilla: PlantillaMeta
    regla: ReglaMetaEntrada | None = None
    recordatorio: RecordatorioEntrada | None = None


class MetaResponse(ModeloContrato):
    meta_id: str
    estado: EstadoMeta

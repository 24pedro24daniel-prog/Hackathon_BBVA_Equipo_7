"""F8 — Plan de salud, score y metas (contrato §8)."""

from pydantic import Field

from app.schemas.common import EstadoMeta, Frecuencia, Meta, ModeloContrato, ModeloEntrada, PlantillaMeta, TipoRegla


class Subindicador(ModeloContrato):
    id: str
    nombre: str
    valor: int = Field(ge=0, le=100)
    detalle: str
    peso: float = Field(ge=0, le=1)
    destacado: bool = False


class PuntoHistorial(ModeloContrato):
    mes: str
    score: int


class Racha(ModeloContrato):
    tipo: str
    valor: int


class MetaActiva(ModeloContrato):
    meta_id: str
    plantilla: PlantillaMeta
    titulo: str
    detalle: str
    acumulado: float
    estado: EstadoMeta


class ScoreCrediticio(ModeloContrato):
    """Bloque ADICIONAL (no reemplaza `score`): estimación del modelo de credit scoring (regresión logística)."""

    disponible: bool
    score: int | None = Field(default=None, ge=0, le=100)
    categoria: str | None = None  # Rojo (0–39) | Amarillo (40–69) | Verde (70–100)
    motivo: str | None = None  # por qué no hay score (modelo no cargó, poca historia)
    rangos: dict[str, str] | None = None
    features: dict[str, float | str | None] | None = None
    features_imputados: list[str] = []
    features_fuera_de_rango: list[str] = []
    ventana_dias: int | None = None
    fundamento: str | None = None
    limites: str | None = None
    meta: Meta


class SaludResponse(ModeloContrato):
    score: int = Field(ge=0, le=100)
    score_anterior: int | None = None
    etapa_actual: str
    etapas: list[str] = []
    subindicadores: list[Subindicador]
    historial: list[PuntoHistorial] = []
    rachas: list[Racha] = []
    metas_activas: list[MetaActiva] = []
    consentimiento_compartir_historial: bool = False
    fundamento: str | None = None
    score_crediticio: ScoreCrediticio | None = None  # EXT: modelo de ML, aparte del score de hábitos
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

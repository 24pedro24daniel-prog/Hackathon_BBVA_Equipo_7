"""F5 — Análisis de ingresos y egresos (contract.md §5). Dueño: B."""
from datetime import date

from pydantic import BaseModel

from app.schemas.common import Dinero


class Grupo(BaseModel):
    clave: str
    monto: Dinero
    participacion_pct: float
    variacion_pct: float | None = None


class PeriodoAnalisis(BaseModel):
    desde: date
    hasta: date


class ComparacionPares(BaseModel):
    metrica: str
    valor_empresa: float
    mediana_pares: float
    grupo_pares: str
    n_pares: int
    nota: str


class AnalisisResponse(BaseModel):
    agrupar_por: str
    tipo: str
    periodo: PeriodoAnalisis | None = None
    grupos: list[Grupo]
    comparacion_pares: ComparacionPares | None = None

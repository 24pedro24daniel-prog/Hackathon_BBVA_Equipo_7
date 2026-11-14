"""F5 — Análisis de ingresos y egresos (contrato §5)."""

from datetime import date
from enum import Enum

from app.schemas.common import Dinero, ModeloContrato


class AgruparPor(str, Enum):
    categoria = "categoria"
    producto = "producto"
    proveedor = "proveedor"
    cliente_fiado = "cliente_fiado"
    metodo_pago = "metodo_pago"
    mes = "mes"


class TipoAnalisis(str, Enum):
    ingreso = "ingreso"
    egreso = "egreso"


class CompararCon(str, Enum):
    periodo_anterior = "periodo_anterior"
    mismo_periodo_anio_anterior = "mismo_periodo_anio_anterior"


class Periodo(ModeloContrato):
    desde: date
    hasta: date


class Grupo(ModeloContrato):
    clave: str
    monto: Dinero
    participacion_pct: float
    variacion_pct: float | None = None


class ComparacionPares(ModeloContrato):
    metrica: str
    valor_empresa: float
    mediana_pares: float
    grupo_pares: str
    n_pares: int
    nota: str


class AnalisisResponse(ModeloContrato):
    agrupar_por: AgruparPor
    tipo: TipoAnalisis
    periodo: Periodo | None = None
    grupos: list[Grupo]
    comparacion_pares: ComparacionPares | None = None

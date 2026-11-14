"""★ INTERFAZ B (PLAN_MVP.md §4.2): funciones públicas de los motores financieros.

Firmas congeladas: cambiarlas = avisar al otro dev + PR pequeño. Agregar campos opcionales a la respuesta sí se puede.
Fase 0: devuelven los JSON del mock del contrato (Pedro). B las reemplaza por el cálculo real (B1–B9) sin
cambiar la firma; mientras tanto A ya puede integrarlas.
"""

from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app import mock_contrato as mock
from app.schemas.common import redondear
from app.schemas.cuentas import ChequeoResponse, EstadoImpuestos, FiadosResponse, PedidosResponse
from app.schemas.forecast import ForecastResponse
from app.schemas.resumen import ResumenResponse
from app.schemas.simulador import Accion, SimulacionResponse

__all__ = [
    "saldo_caja",
    "fiados",
    "pedidos",
    "estado_impuestos",
    "resumen",
    "forecast",
    "chequeo_pedido",
    "simular",
]


def saldo_caja(db: Session, empresa_id: str, fecha_corte: date | None = None) -> Decimal:
    return redondear(mock.SALDO_NEGOCIO)


def fiados(db: Session, empresa_id: str, estado: str = "pendiente", fecha_corte: date | None = None) -> FiadosResponse:
    return FiadosResponse.model_validate(mock.fiados())


def pedidos(db: Session, empresa_id: str, estado: str = "pendiente", fecha_corte: date | None = None) -> PedidosResponse:
    return PedidosResponse.model_validate(mock.pedidos())


def estado_impuestos(db: Session, empresa_id: str, fecha_corte: date | None = None) -> EstadoImpuestos:
    return EstadoImpuestos.model_validate(mock.estado_impuestos())


def resumen(db: Session, empresa_id: str, periodo: str, fecha_corte: date | None = None) -> ResumenResponse:
    return ResumenResponse.model_validate(mock.resumen(periodo))


def forecast(db: Session, empresa_id: str, horizonte_dias: int = 30, fecha_corte: date | None = None) -> ForecastResponse:
    return ForecastResponse.model_validate(mock.forecast(horizonte_dias))


def chequeo_pedido(
    db: Session, empresa_id: str, proveedor: str, monto: Decimal, fecha_vencimiento: date
) -> ChequeoResponse:
    return ChequeoResponse.model_validate(mock.chequeo(float(monto)))


def simular(db: Session, empresa_id: str, acciones: list[Accion]) -> SimulacionResponse:
    crudas = [a.model_dump(mode="json") if isinstance(a, Accion) else dict(a) for a in acciones]
    return SimulacionResponse.model_validate(mock.simulacion(crudas))

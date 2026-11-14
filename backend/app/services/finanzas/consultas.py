"""B1 — Consultas a fecha de corte: saldo, fiados, pedidos (deudas) e impuestos.

FASE 0: devuelven el mock de Pedro. Reemplazar por SQL real (filtrando creado_en < fecha_corte).
"""
from datetime import date
from decimal import Decimal

from app.core.meta import construir_meta
from app.mocks import data as mock
from app.schemas.cuentas import EstadoImpuestos, FiadosResponse, PedidosResponse


def saldo_caja(db, empresa_id: str, fecha_corte: date | None = None) -> Decimal:
    return Decimal(str(mock.ESTADO["saldo"])).quantize(Decimal("0.01"))


def fiados(db, empresa_id: str, estado: str = "pendiente", fecha_corte: date | None = None) -> FiadosResponse:
    return FiadosResponse.model_validate(
        {**mock.fiados_pedro(), "meta": construir_meta("riesgo-atraso-clf", "0.2.0")}
    )


def pedidos(db, empresa_id: str, estado: str = "pendiente", fecha_corte: date | None = None) -> PedidosResponse:
    return PedidosResponse.model_validate(mock.pedidos_pedro())


def estado_impuestos(db, empresa_id: str, fecha_corte: date | None = None) -> EstadoImpuestos:
    return EstadoImpuestos.model_validate(mock.impuestos_pedro())

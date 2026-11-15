"""Movimientos: consulta y registro manual (contrato §2)."""

from datetime import datetime

from app.schemas.common import Canal, Dinero, MetodoPago, ModeloContrato, TipoMovimiento
from app.schemas.ingesta import MovimientoPropuesto


class LineaMovimiento(ModeloContrato):
    """Una línea del detalle del movimiento (qué se vendió o compró)."""

    producto: str | None = None
    cantidad: float
    precio_unitario: Dinero
    subtotal: Dinero


class MovimientoItem(ModeloContrato):
    movimiento_id: str
    fecha_hora: datetime
    tipo: TipoMovimiento
    categoria: str | None = None
    monto: Dinero
    moneda: str = "PEN"
    metodo_pago: MetodoPago
    contraparte: str | None = None
    canal: Canal
    confianza_extraccion: float | None = None
    afecta_caja: bool
    saldo_post: Dinero | None = None
    descripcion: str | None = None
    items: list[LineaMovimiento] = []


class MovimientosResponse(ModeloContrato):
    items: list[MovimientoItem]
    next_cursor: str | None = None


class MovimientoManualRequest(MovimientoPropuesto):
    """Mismo esquema que movimiento_propuesto (canal = manual, sin borrador)."""

"""F4 — Fiados, pedidos, chequeo y recordatorio (contract.md §4.3–4.5). Dueño: B."""
from datetime import date

from pydantic import BaseModel, Field

from app.schemas.common import Confianza, Dinero, EstadoCaja, EstadoCuenta, Meta, NivelRiesgo


class RiesgoAtraso(BaseModel):
    probabilidad: float
    nivel: NivelRiesgo
    baseline_probabilidad: float | None = None


class AccionSugerida(BaseModel):
    tipo: str
    texto_boton: str


class FiadoItem(BaseModel):
    fiado_id: str
    cliente_id: str
    cliente: str
    detalle: str | None = None  # EXT
    monto: Dinero
    fecha: date
    dias_transcurridos: int
    estado: EstadoCuenta
    riesgo_atraso: RiesgoAtraso
    accion_sugerida: AccionSugerida | None = None


class FiadosResponse(BaseModel):
    total_pendiente: Dinero
    total_vencido: Dinero
    items: list[FiadoItem]
    fundamento: str | None = None  # EXT
    limites: str | None = None     # EXT
    meta: Meta


class RecordatorioResponse(BaseModel):
    mensaje: str


class PedidoItem(BaseModel):
    pedido_id: str
    proveedor: str
    monto: Dinero
    monto_pendiente: Dinero
    fecha_pedido: date
    fecha_vencimiento: date
    estado: EstadoCuenta
    dias_para_vencer: int


class EstadoImpuestos(BaseModel):
    estado: str  # al_dia | vencido | pendiente
    proximo_vencimiento: date | None = None
    monto_estimado: Dinero | None = None
    nombre: str | None = None  # EXT


class PedidosResponse(BaseModel):
    total_pendiente: Dinero
    items: list[PedidoItem]
    impuestos: EstadoImpuestos


class ChequeoRequest(BaseModel):
    proveedor: str = Field(min_length=1)
    monto: Dinero
    fecha_vencimiento: date


class Sugerencia(BaseModel):
    accion: str  # reducir_pedido | pagar_en_partes | combinar
    monto_sugerido: Dinero | None = None
    partes: int | None = None
    detalle: str | None = None
    saldo_resultante: Dinero


class ChequeoResponse(BaseModel):
    saldo_proyectado_al_vencimiento: Dinero
    estado_caja: EstadoCaja
    venta_esperada_periodo: Dinero
    exceso_vs_ventas: Dinero
    sugerencias: list[Sugerencia]
    fundamento: str
    limites: str
    confianza: Confianza
    meta: Meta

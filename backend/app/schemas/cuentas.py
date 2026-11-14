"""F4 — Fiados, pedidos/cuentas por pagar, chequeo antes del pedido y recordatorio (contrato §4.3–4.5)."""

from datetime import date

from pydantic import Field

from app.schemas.common import Confianza, Dinero, EstadoCaja, EstadoCuenta, Meta, ModeloContrato, ModeloEntrada, NivelRiesgo


class RiesgoAtraso(ModeloContrato):
    probabilidad: float
    nivel: NivelRiesgo
    baseline_probabilidad: float | None = None


class AccionSugerida(ModeloContrato):
    tipo: str
    texto_boton: str


class FiadoItem(ModeloContrato):
    fiado_id: str
    cliente_id: str
    cliente: str
    monto: Dinero
    fecha: date
    dias_transcurridos: int
    estado: EstadoCuenta
    riesgo_atraso: RiesgoAtraso | None = None
    accion_sugerida: AccionSugerida | None = None


class FiadosResponse(ModeloContrato):
    total_pendiente: Dinero
    total_vencido: Dinero
    items: list[FiadoItem]
    meta: Meta


class RecordatorioResponse(ModeloContrato):
    mensaje: str


class EstadoImpuestos(ModeloContrato):
    estado: str  # al_dia | vencido
    proximo_vencimiento: date | None = None
    monto_estimado: Dinero | None = None


class PedidoItem(ModeloContrato):
    pedido_id: str
    proveedor: str
    monto: Dinero
    monto_pendiente: Dinero
    fecha_pedido: date
    fecha_vencimiento: date
    estado: EstadoCuenta
    dias_para_vencer: int


class PedidosResponse(ModeloContrato):
    total_pendiente: Dinero
    items: list[PedidoItem]
    impuestos: EstadoImpuestos


class ChequeoRequest(ModeloEntrada):
    proveedor: str = Field(min_length=1, max_length=100)
    monto: Dinero = Field(gt=0)
    fecha_vencimiento: date


class Sugerencia(ModeloContrato):
    accion: str
    saldo_resultante: Dinero
    monto_sugerido: Dinero | None = None
    partes: int | None = None
    detalle: str | None = None


class ChequeoResponse(ModeloContrato):
    saldo_proyectado_al_vencimiento: Dinero
    estado_caja: EstadoCaja
    venta_esperada_periodo: Dinero
    exceso_vs_ventas: Dinero
    sugerencias: list[Sugerencia]
    fundamento: str
    limites: str
    confianza: Confianza
    meta: Meta

"""Enums del contrato, Meta, Error y Dinero. Compartido: se congela tras la Fase 0."""
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, PlainSerializer


# ---------- Dinero: Decimal internamente, número con 2 decimales en el JSON ----------
def _a_decimal(v: Any) -> Any:
    if v is None or isinstance(v, bool):
        return v
    if isinstance(v, (int, float, str, Decimal)):
        return Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return v


Dinero = Annotated[
    Decimal,
    BeforeValidator(_a_decimal),
    PlainSerializer(lambda v: float(v), return_type=float, when_used="json"),
]


# ---------- Enums compartidos (contract.md §0) ----------
class TipoMovimiento(StrEnum):
    # ingresos
    venta = "venta"
    cobro_fiado = "cobro_fiado"
    prestamo_recibido = "prestamo_recibido"
    otro_ingreso = "otro_ingreso"
    # egresos
    compra = "compra"
    gasto_negocio = "gasto_negocio"
    retiro_personal = "retiro_personal"
    pago_proveedor = "pago_proveedor"
    pago_prestamo = "pago_prestamo"
    pago_impuesto = "pago_impuesto"


class MetodoPago(StrEnum):
    efectivo = "efectivo"
    billetera_digital = "billetera_digital"
    transferencia = "transferencia"
    tarjeta = "tarjeta"
    credito = "credito"  # fiado o pedido a crédito: no mueve caja


class TipoDeuda(StrEnum):
    proveedor = "proveedor"
    prestamo_informal = "prestamo_informal"
    familiar = "familiar"
    entidad_financiera = "entidad_financiera"


class Canal(StrEnum):
    voz = "voz"
    texto = "texto"
    foto = "foto"
    billetera_api = "billetera_api"
    manual = "manual"


class EstadoCuenta(StrEnum):
    pendiente = "pendiente"
    por_vencer = "por_vencer"
    vencido = "vencido"
    pagado = "pagado"


class NivelRiesgo(StrEnum):
    bajo = "bajo"
    medio = "medio"
    alto = "alto"


class EstadoCaja(StrEnum):
    te_alcanza = "te_alcanza"
    justo = "justo"
    no_te_alcanza = "no_te_alcanza"


class TipoAlerta(StrEnum):
    faltante_caja = "faltante_caja"
    pedido_excesivo = "pedido_excesivo"
    retiro_excesivo = "retiro_excesivo"
    obligacion_proxima = "obligacion_proxima"
    gasto_inusual = "gasto_inusual"
    caida_ventas = "caida_ventas"
    fiado_vencido = "fiado_vencido"
    meta_lograda = "meta_lograda"
    resumen_semanal = "resumen_semanal"


class Confianza(StrEnum):
    baja = "baja"
    media = "media"
    alta = "alta"


class TipoAccionSimulador(StrEnum):
    reducir_pedido = "reducir_pedido"
    pagar_en_partes = "pagar_en_partes"
    diferir_pago = "diferir_pago"
    cobrar_fiados = "cobrar_fiados"
    limitar_retiros = "limitar_retiros"
    ajustar_gasto = "ajustar_gasto"


# ---------- Meta y errores ----------
class Meta(BaseModel):
    request_id: str
    generado_en: datetime
    modelo: str
    modelo_version: str
    prompt_version: str | None = None
    fallback_usado: bool = False
    latencia_ms: int = 0


class ErrorDetalle(BaseModel):
    campo: str | None = None
    problema: str


class ErrorCuerpo(BaseModel):
    codigo: str
    mensaje: str
    detalles: list[ErrorDetalle] = []
    request_id: str


class ErrorResponse(BaseModel):
    error: ErrorCuerpo

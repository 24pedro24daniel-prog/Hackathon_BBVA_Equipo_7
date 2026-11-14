"""F1 — Ingesta: webhook, interpretar, confirmar, cuaderno e impuestos (contrato §1)."""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.common import (
    Canal,
    Dinero,
    Frecuencia,
    Meta,
    MetodoPago,
    ModeloContrato,
    ModeloEntrada,
    OrigenMonto,
    RegistroCreado,
    TipoMensajeWebhook,
    TipoMovimiento,
)


class ItemMovimiento(BaseModel):
    model_config = ConfigDict(extra="forbid")

    producto_id: str | None = None
    producto: str | None = None
    cantidad: Decimal = Field(gt=0)
    precio_unitario: Dinero = Field(ge=0)
    subtotal: Dinero = Field(ge=0)


class MovimientoPropuesto(BaseModel):
    """Lo que entendió el extractor (o lo que manda el formulario manual). Estricto con los campos."""

    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    tipo: TipoMovimiento
    items: list[ItemMovimiento] = []
    monto: Dinero = Field(gt=0)
    moneda: str = Field(default="PEN", pattern="^PEN$")
    metodo_pago: MetodoPago | None = None
    contraparte: str | None = Field(default=None, max_length=100)
    fecha_hora: datetime | None = None
    fecha_vencimiento: date | None = None
    # Opcionales (extensión): ayudan al registrador en préstamos, cobros y categorías.
    descripcion: str | None = Field(default=None, max_length=255)
    categoria: str | None = None
    fiado_id: str | None = None
    deuda_id: str | None = None
    impuesto_id: str | None = None
    monto_total_a_pagar: Dinero | None = Field(default=None, gt=0)
    frecuencia_cuota: Frecuencia | None = None
    monto_cuota: Dinero | None = Field(default=None, gt=0)


class MovimientoBorrador(MovimientoPropuesto):
    """Lo que sale de /interpretar: igual que MovimientoPropuesto, pero el monto puede faltar (campos_faltantes)."""

    monto: Dinero | None = Field(default=None, gt=0)


class RegistroResultado(ModeloContrato):
    movimiento_id: str
    registros_creados: list[RegistroCreado]


# ── /webhooks/whatsapp ──


class WebhookRequest(ModeloEntrada):
    telefono_hash: str = Field(min_length=1, max_length=128)
    empresa_id: str | None = None
    tipo: TipoMensajeWebhook
    texto: str | None = None
    media_url: str | None = Field(default=None, max_length=255)
    recibido_en: datetime | None = None
    mensaje_id: str | None = Field(default=None, max_length=100)


class Boton(ModeloContrato):
    id: str
    texto: str


class WebhookResponse(ModeloContrato):
    respuesta_texto: str
    botones: list[Boton] = []
    respuesta_audio_url: str | None = None


# ── /ingesta/interpretar ──


class InterpretarRequest(ModeloEntrada):
    empresa_id: str
    canal: Canal
    texto: str | None = Field(default=None, max_length=2000)
    media_url: str | None = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def _texto_o_media(self):
        if not (self.texto and self.texto.strip()) and not self.media_url:
            raise ValueError("Envía 'texto' o 'media_url'")
        return self


class InterpretarResponse(ModeloContrato):
    borrador_id: str
    transcripcion: str | None = None
    movimiento_propuesto: MovimientoBorrador
    origen_monto: OrigenMonto
    confianza: float = Field(ge=0, le=1)
    campos_faltantes: list[str] = []
    pregunta_aclaratoria: str | None = None
    meta: Meta


# ── /ingesta/confirmar ──


class ConfirmarRequest(ModeloEntrada):
    borrador_id: str
    confirmado: bool = True
    correcciones: dict = {}


class ConfirmarResponse(ModeloContrato):
    movimiento_id: str
    registros_creados: list[RegistroCreado]
    alertas_disparadas: list[dict] = []
    saldo_caja_negocio: Dinero


# ── /ingesta/cuaderno ──


class CuadernoRequest(ModeloEntrada):
    empresa_id: str
    media_url: str = Field(min_length=1, max_length=255)


class FiadoPropuesto(ModeloContrato):
    cliente: str
    detalle: str | None = None
    monto: Dinero
    fecha: date
    confianza: float = Field(ge=0, le=1)
    cliente_id: str | None = None
    cliente_nuevo: bool | None = None
    posible_duplicado: bool | None = None


class CuadernoResponse(ModeloContrato):
    borrador_id: str
    fiados_propuestos: list[FiadoPropuesto]
    lineas_no_legibles: int = 0
    lineas_tachadas: int = 0
    meta: Meta


# ── /empresas/{id}/impuestos ──


class ImpuestoRequest(ModeloEntrada):
    periodo: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    regimen: str = Field(default="nuevo_rus", max_length=20)
    pagado: bool
    monto: Dinero = Field(ge=0)
    fecha_pago: date | None = None


class ImpuestoResponse(ModeloContrato):
    impuesto_id: str
    estado: str
    proximo_vencimiento: date | None = None

"""Tipos compartidos del contrato (contract.md §0) y enums del modelo de datos (modelo_datos.dbml).

Fuente única de los enums: los modelos de SQLAlchemy también los importan de aquí.
"""

from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from enum import Enum
from typing import Annotated, Any

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, PlainSerializer

# ── Dinero: Decimal con 2 decimales; en JSON sale como número (2340.0) ──────────────────────────

CENTAVO = Decimal("0.01")


def redondear(valor: Decimal | float | int | str) -> Decimal:
    return Decimal(str(valor)).quantize(CENTAVO, rounding=ROUND_HALF_UP)


Dinero = Annotated[
    Decimal,
    AfterValidator(redondear),
    PlainSerializer(lambda d: float(d), return_type=float, when_used="json"),
]
Cantidad = Annotated[  # unidades de un producto (puede ser fraccionaria): en JSON sale como número, no como texto
    Decimal,
    PlainSerializer(lambda d: float(d), return_type=float, when_used="json"),
]
Probabilidad = Annotated[
    Decimal,
    Field(ge=0, le=1),
    PlainSerializer(lambda d: float(d), return_type=float, when_used="json"),
]


class ModeloContrato(BaseModel):
    """Base de las respuestas: acepta campos extra (las extensiones EXT que usa el front)."""

    model_config = ConfigDict(extra="allow", use_enum_values=True)


class ModeloEntrada(BaseModel):
    """Base de los requests: rechaza campos desconocidos para detectar errores del cliente."""

    model_config = ConfigDict(extra="forbid", use_enum_values=True)


# ── Enums del contrato ──────────────────────────────────────────────────────────────────────────


class TipoMovimiento(str, Enum):
    venta = "venta"
    cobro_fiado = "cobro_fiado"
    prestamo_recibido = "prestamo_recibido"
    otro_ingreso = "otro_ingreso"
    compra = "compra"
    gasto_negocio = "gasto_negocio"
    retiro_personal = "retiro_personal"
    pago_proveedor = "pago_proveedor"
    pago_prestamo = "pago_prestamo"
    pago_impuesto = "pago_impuesto"


TIPOS_INGRESO = frozenset(
    {TipoMovimiento.venta, TipoMovimiento.cobro_fiado, TipoMovimiento.prestamo_recibido, TipoMovimiento.otro_ingreso}
)
TIPOS_EGRESO = frozenset(set(TipoMovimiento) - TIPOS_INGRESO)


def signo(tipo: TipoMovimiento | str) -> int:
    """+1 para ingresos, −1 para egresos (el monto siempre se guarda positivo)."""
    return 1 if TipoMovimiento(tipo) in TIPOS_INGRESO else -1


class MetodoPago(str, Enum):
    efectivo = "efectivo"
    billetera_digital = "billetera_digital"
    transferencia = "transferencia"
    tarjeta = "tarjeta"
    credito = "credito"


class TipoDeuda(str, Enum):
    proveedor = "proveedor"
    prestamo_informal = "prestamo_informal"
    familiar = "familiar"
    entidad_financiera = "entidad_financiera"


class Canal(str, Enum):
    """canal_registro del DBML."""

    voz = "voz"
    texto = "texto"
    foto = "foto"
    billetera_api = "billetera_api"
    manual = "manual"


class EstadoCuenta(str, Enum):
    pendiente = "pendiente"
    por_vencer = "por_vencer"
    vencido = "vencido"
    pagado = "pagado"


class NivelRiesgo(str, Enum):
    bajo = "bajo"
    medio = "medio"
    alto = "alto"


class EstadoCaja(str, Enum):
    te_alcanza = "te_alcanza"
    justo = "justo"
    no_te_alcanza = "no_te_alcanza"


class TipoAlerta(str, Enum):
    faltante_caja = "faltante_caja"
    pedido_excesivo = "pedido_excesivo"
    retiro_excesivo = "retiro_excesivo"
    obligacion_proxima = "obligacion_proxima"
    gasto_inusual = "gasto_inusual"
    caida_ventas = "caida_ventas"
    fiado_vencido = "fiado_vencido"
    meta_lograda = "meta_lograda"
    resumen_semanal = "resumen_semanal"


PRIORIDAD_ALERTA = {
    TipoAlerta.faltante_caja: 1,
    TipoAlerta.pedido_excesivo: 2,
    TipoAlerta.retiro_excesivo: 3,
    TipoAlerta.obligacion_proxima: 4,
    TipoAlerta.gasto_inusual: 5,
    TipoAlerta.caida_ventas: 5,
    TipoAlerta.fiado_vencido: 6,
    TipoAlerta.meta_lograda: 7,
    TipoAlerta.resumen_semanal: 8,
}


class OrigenMonto(str, Enum):
    dicho_por_usuario = "dicho_por_usuario"
    catalogo = "catalogo"
    estimado = "estimado"


class TipoMensajeWebhook(str, Enum):
    texto = "texto"
    audio = "audio"
    imagen = "imagen"
    boton = "boton"


class IntencionAsistente(str, Enum):
    estado_caja = "estado_caja"
    explicar_alerta = "explicar_alerta"
    simular = "simular"
    concepto = "concepto"
    crear_meta = "crear_meta"
    prestamo = "prestamo"
    fuera_de_alcance = "fuera_de_alcance"
    otro = "otro"


class TipoAccionSimulador(str, Enum):
    reducir_pedido = "reducir_pedido"
    pagar_en_partes = "pagar_en_partes"
    diferir_pago = "diferir_pago"
    cobrar_fiados = "cobrar_fiados"
    limitar_retiros = "limitar_retiros"
    ajustar_gasto = "ajustar_gasto"


class AccionAlerta(str, Enum):
    ejecutada = "ejecutada"
    descartada = "descartada"
    posponer = "posponer"


class Confianza(str, Enum):
    """Confianza cualitativa de una recomendación (fundamento / limites / confianza)."""

    baja = "baja"
    media = "media"
    alta = "alta"


# ── Enums solo del modelo de datos ──────────────────────────────────────────────────────────────


class TipoFlujo(str, Enum):
    ingreso = "ingreso"
    egreso = "egreso"


class EstadoBorrador(str, Enum):
    pendiente = "pendiente"
    confirmado = "confirmado"
    descartado = "descartado"


class Frecuencia(str, Enum):
    diaria = "diaria"
    semanal = "semanal"
    quincenal = "quincenal"
    mensual = "mensual"


class OrigenBilletera(str, Enum):
    api = "api"
    captura = "captura"


class PlantillaMeta(str, Enum):
    registrar_30_dias = "registrar_30_dias"
    sueldo_fijo = "sueldo_fijo"
    colchon_caja = "colchon_caja"
    apartar_para_pedido = "apartar_para_pedido"
    reservar_impuestos = "reservar_impuestos"


class TipoRegla(str, Enum):
    porcentaje_de_venta = "porcentaje_de_venta"
    monto_fijo = "monto_fijo"


class EstadoMeta(str, Enum):
    activa = "activa"
    lograda = "lograda"
    pausada = "pausada"


class CanalNotificacion(str, Enum):
    whatsapp = "whatsapp"
    app = "app"
    email = "email"


class EstadoAlerta(str, Enum):
    activa = "activa"
    atendida = "atendida"
    descartada = "descartada"


class RolMensaje(str, Enum):
    usuario = "usuario"
    asistente = "asistente"


class PerfilPago(str, Enum):
    """OCULTO: solo lo usa el generador sintético. Nunca es feature."""

    puntual = "puntual"
    ocasional = "ocasional"
    moroso = "moroso"


class TipoEvento(str, Enum):
    cliente_no_paga = "cliente_no_paga"
    mes_bajo = "mes_bajo"
    alza_proveedor = "alza_proveedor"
    gasto_extra = "gasto_extra"
    retiro_excesivo = "retiro_excesivo"


# ── Bloques comunes ─────────────────────────────────────────────────────────────────────────────


class Meta(ModeloContrato):
    request_id: str | None = None
    generado_en: datetime | None = None
    modelo: str | None = None
    modelo_version: str | None = None
    prompt_version: str | None = None
    fallback_usado: bool = False
    latencia_ms: int | None = None


class ErrorDetalle(BaseModel):
    campo: str
    problema: str


class ErrorCuerpo(BaseModel):
    codigo: str
    mensaje: str
    detalles: list[ErrorDetalle | dict[str, Any]] = []
    request_id: str | None = None


class ErrorResponse(BaseModel):
    error: ErrorCuerpo


class RegistroCreado(ModeloContrato):
    tabla: str
    id: str

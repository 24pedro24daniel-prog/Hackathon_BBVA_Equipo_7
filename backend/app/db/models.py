"""Las 27 tablas del esquema: las 25 del modelo de negocio de modelo_datos.dbml + las 2 técnicas (idempotency_keys y llm_llamadas).

data/schema.sql y data/schema_esquema.json se GENERAN desde este archivo (data/pipeline_python/generar_schema.py).

Reglas: dinero Numeric(12,2) → Decimal; probabilidades y confianzas Numeric(4,3); fecha-hora timestamptz.
Nada calculado se guarda (saldo, pendiente, atraso, estados): sale de services/finanzas/consultas.py.
"""

from datetime import date, datetime, time
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    Time,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import CHAR
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, pg_enum
from app.schemas.common import (
    Canal,
    CanalNotificacion,
    EstadoAlerta,
    EstadoBorrador,
    EstadoMeta,
    Frecuencia,
    MetodoPago,
    NivelRiesgo,
    OrigenBilletera,
    OrigenMonto,
    PerfilPago,
    PlantillaMeta,
    RolMensaje,
    TipoAlerta,
    TipoDeuda,
    TipoEvento,
    TipoFlujo,
    TipoMovimiento,
    TipoRegla,
)

# Tipos de PostgreSQL compartidos (un solo CREATE TYPE por enum)
T_TIPO_FLUJO = pg_enum(TipoFlujo, "tipo_flujo")
T_TIPO_MOVIMIENTO = pg_enum(TipoMovimiento, "tipo_movimiento")
T_METODO_PAGO = pg_enum(MetodoPago, "metodo_pago")
T_CANAL = pg_enum(Canal, "canal_registro")
T_ORIGEN_MONTO = pg_enum(OrigenMonto, "origen_monto")
T_ESTADO_BORRADOR = pg_enum(EstadoBorrador, "estado_borrador")
T_TIPO_DEUDA = pg_enum(TipoDeuda, "tipo_deuda")
T_FRECUENCIA = pg_enum(Frecuencia, "frecuencia")
T_ORIGEN_BILLETERA = pg_enum(OrigenBilletera, "origen_billetera")
T_PLANTILLA_META = pg_enum(PlantillaMeta, "plantilla_meta")
T_TIPO_REGLA = pg_enum(TipoRegla, "tipo_regla")
T_ESTADO_META = pg_enum(EstadoMeta, "estado_meta")
T_TIPO_ALERTA = pg_enum(TipoAlerta, "tipo_alerta")
T_NIVEL_RIESGO = pg_enum(NivelRiesgo, "nivel_riesgo")
T_CANAL_NOTIF = pg_enum(CanalNotificacion, "canal_notificacion")
T_ESTADO_ALERTA = pg_enum(EstadoAlerta, "estado_alerta")
T_ROL = pg_enum(RolMensaje, "rol_mensaje")
T_PERFIL_PAGO = pg_enum(PerfilPago, "perfil_pago")
T_TIPO_EVENTO = pg_enum(TipoEvento, "tipo_evento")

PROB = Numeric(4, 3)


def _id(**kw) -> Any:
    return mapped_column(String(20), primary_key=True, **kw)


def _fk(destino: str, nullable: bool = False, **kw) -> Any:
    return mapped_column(String(20), ForeignKey(destino), nullable=nullable, **kw)


def _entre_0_y_1(columna: str) -> CheckConstraint:
    return CheckConstraint(f"{columna} IS NULL OR ({columna} >= 0 AND {columna} <= 1)", name=f"{columna}_0_1")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ MAESTRAS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class Rubro(Base):
    __tablename__ = "rubros"

    rubro_id: Mapped[str] = _id()
    nombre: Mapped[str] = mapped_column(String(50), unique=True)


class Empresa(Base):
    __tablename__ = "empresas"
    __table_args__ = (
        CheckConstraint("n_trabajadores >= 1", name="n_trabajadores_positivo"),
        CheckConstraint("minimo_operativo >= 0", name="minimo_operativo_no_negativo"),
        CheckConstraint("saldo_inicial >= 0", name="saldo_inicial_no_negativo"),
        CheckConstraint("ruc IS NULL OR ruc ~ '^10[0-9]{9}$'", name="ruc_formato"),
    )

    empresa_id: Mapped[str] = _id()
    rubro_id: Mapped[str] = _fk("rubros.rubro_id")
    nombre_ficticio: Mapped[str] = mapped_column(String(100))
    telefono_whatsapp: Mapped[str] = mapped_column(String(20), unique=True)
    zona: Mapped[str] = mapped_column(String(50))
    n_trabajadores: Mapped[int] = mapped_column(SmallInteger, default=1, server_default=text("1"))
    tiene_ruc: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    # RUC de persona natural (10 + 9 dígitos). Viene de data/csv; el backend no lo usa.
    ruc: Mapped[str | None] = mapped_column(String(11), unique=True)
    regimen_tributario: Mapped[str | None] = mapped_column(String(20))
    saldo_inicial: Mapped[Decimal]
    fecha_saldo_inicial: Mapped[date]
    minimo_operativo: Mapped[Decimal]
    fecha_alta: Mapped[datetime]


class PreferenciasAlertas(Base):
    __tablename__ = "preferencias_alertas"
    __table_args__ = (CheckConstraint("max_por_dia >= 0", name="max_por_dia_no_negativo"),)

    empresa_id: Mapped[str] = mapped_column(String(20), ForeignKey("empresas.empresa_id"), primary_key=True)
    canales: Mapped[list] = mapped_column(JSON)
    max_por_dia: Mapped[int] = mapped_column(SmallInteger, default=2, server_default=text("2"))
    silencio_desde: Mapped[time] = mapped_column(Time, default=time(21, 0), server_default=text("'21:00'"))
    silencio_hasta: Mapped[time] = mapped_column(Time, default=time(7, 0), server_default=text("'07:00'"))
    resumen_semanal: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))


class Categoria(Base):
    __tablename__ = "categorias"

    categoria_id: Mapped[str] = _id()
    nombre: Mapped[str] = mapped_column(String(50), unique=True)
    tipo: Mapped[TipoFlujo] = mapped_column(T_TIPO_FLUJO)
    es_del_negocio: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))


class Producto(Base):
    __tablename__ = "productos"
    __table_args__ = (
        CheckConstraint("precio_venta > 0", name="precio_venta_positivo"),
        CheckConstraint("costo_unitario IS NULL OR costo_unitario >= 0", name="costo_no_negativo"),
    )

    producto_id: Mapped[str] = _id()
    empresa_id: Mapped[str] = _fk("empresas.empresa_id")
    categoria_id: Mapped[str] = _fk("categorias.categoria_id")
    nombre: Mapped[str] = mapped_column(String(100))
    alias: Mapped[list | None] = mapped_column(JSON)
    precio_venta: Mapped[Decimal]
    costo_unitario: Mapped[Decimal | None]
    activo: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))


class Cliente(Base):
    __tablename__ = "clientes"

    cliente_id: Mapped[str] = _id()
    empresa_id: Mapped[str] = _fk("empresas.empresa_id")
    nombre_ficticio: Mapped[str] = mapped_column(String(100))
    alias: Mapped[list | None] = mapped_column(JSON)
    telefono_ficticio: Mapped[str | None] = mapped_column(String(20))
    perfil_pago: Mapped[PerfilPago | None] = mapped_column(T_PERFIL_PAGO, comment="OCULTO: nunca es feature")
    creado_en: Mapped[datetime]


class Proveedor(Base):
    __tablename__ = "proveedores"
    __table_args__ = (CheckConstraint("plazo_pago_dias >= 0", name="plazo_no_negativo"),)

    proveedor_id: Mapped[str] = _id()
    empresa_id: Mapped[str] = _fk("empresas.empresa_id")
    nombre_ficticio: Mapped[str] = mapped_column(String(100))
    telefono_ficticio: Mapped[str | None] = mapped_column(String(20))
    plazo_pago_dias: Mapped[int] = mapped_column(SmallInteger)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ INGESTA Y TRANSACCIONES ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class Borrador(Base):
    __tablename__ = "borradores"
    __table_args__ = (_entre_0_y_1("confianza"),)

    borrador_id: Mapped[str] = _id()
    empresa_id: Mapped[str] = _fk("empresas.empresa_id")
    mensaje_id: Mapped[str | None] = _fk("conversaciones.mensaje_id", nullable=True)
    canal: Mapped[Canal] = mapped_column(T_CANAL)
    media_url: Mapped[str | None] = mapped_column(String(255))
    texto_original: Mapped[str | None] = mapped_column(Text)
    payload_propuesto: Mapped[Any] = mapped_column(JSON)
    origen_monto: Mapped[OrigenMonto | None] = mapped_column(T_ORIGEN_MONTO)
    confianza: Mapped[Decimal | None] = mapped_column(PROB)
    campos_faltantes: Mapped[list | None] = mapped_column(JSON)
    pregunta_aclaratoria: Mapped[str | None] = mapped_column(Text)
    correcciones: Mapped[dict | None] = mapped_column(JSON)
    estado: Mapped[EstadoBorrador] = mapped_column(
        T_ESTADO_BORRADOR, default=EstadoBorrador.pendiente, server_default=text("'pendiente'")
    )
    modelo_version: Mapped[str | None] = mapped_column(String(30))
    prompt_version: Mapped[str | None] = mapped_column(String(30))
    fallback_usado: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    creado_en: Mapped[datetime]
    resuelto_en: Mapped[datetime | None]


class Transaccion(Base):
    __tablename__ = "transacciones"
    __table_args__ = (
        CheckConstraint("monto > 0", name="monto_positivo"),
        CheckConstraint("afecta_caja = (metodo_pago <> 'credito')", name="afecta_caja_segun_metodo"),
        CheckConstraint("num_nonnulls(fiado_id, deuda_id, impuesto_id, programado_id) <= 1", name="un_solo_vinculo"),
        CheckConstraint("tipo <> 'cobro_fiado' OR fiado_id IS NOT NULL", name="cobro_fiado_con_fiado"),
        CheckConstraint(
            "tipo NOT IN ('pago_proveedor', 'pago_prestamo', 'prestamo_recibido') OR deuda_id IS NOT NULL",
            name="pago_o_prestamo_con_deuda",
        ),
        CheckConstraint("tipo <> 'pago_impuesto' OR impuesto_id IS NOT NULL", name="pago_impuesto_con_impuesto"),
        CheckConstraint(
            "NOT (tipo = 'venta' AND metodo_pago = 'credito') OR fiado_id IS NOT NULL", name="venta_fiada_con_fiado"
        ),
        CheckConstraint(
            "NOT (tipo = 'compra' AND metodo_pago = 'credito') OR deuda_id IS NOT NULL", name="compra_credito_con_deuda"
        ),
        CheckConstraint("moneda = 'PEN'", name="moneda_pen"),
        _entre_0_y_1("confianza_extraccion"),
        Index(None, "empresa_id", "fecha_hora"),
        Index(None, "empresa_id", "tipo"),
    )

    transaccion_id: Mapped[str] = _id()
    empresa_id: Mapped[str] = _fk("empresas.empresa_id")
    borrador_id: Mapped[str | None] = _fk("borradores.borrador_id", nullable=True)
    fecha_hora: Mapped[datetime]
    tipo: Mapped[TipoMovimiento] = mapped_column(T_TIPO_MOVIMIENTO)
    categoria_id: Mapped[str] = _fk("categorias.categoria_id")
    descripcion: Mapped[str | None] = mapped_column(String(255))
    monto: Mapped[Decimal]
    moneda: Mapped[str] = mapped_column(CHAR(3), default="PEN", server_default=text("'PEN'"))
    metodo_pago: Mapped[MetodoPago] = mapped_column(T_METODO_PAGO)
    afecta_caja: Mapped[bool] = mapped_column(Boolean)
    canal: Mapped[Canal] = mapped_column(T_CANAL)
    confianza_extraccion: Mapped[Decimal | None] = mapped_column(PROB)
    fue_corregida: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    fiado_id: Mapped[str | None] = _fk("cuaderno_fiado.fiado_id", nullable=True)
    deuda_id: Mapped[str | None] = _fk("deudas.deuda_id", nullable=True)
    impuesto_id: Mapped[str | None] = _fk("impuestos.impuesto_id", nullable=True, unique=True)
    programado_id: Mapped[str | None] = _fk("movimientos_programados.programado_id", nullable=True)
    billetera_mov_id: Mapped[str | None] = _fk("billeteras_digitales.billetera_mov_id", nullable=True, unique=True)
    anulada: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    creado_en: Mapped[datetime]


class DetalleTransaccion(Base):
    __tablename__ = "detalle_transaccion"
    __table_args__ = (
        CheckConstraint("cantidad > 0", name="cantidad_positiva"),
        CheckConstraint("precio_unitario >= 0", name="precio_no_negativo"),
        CheckConstraint("subtotal >= 0", name="subtotal_no_negativo"),
        CheckConstraint("costo_unitario IS NULL OR costo_unitario >= 0", name="costo_no_negativo"),
    )

    detalle_id: Mapped[str] = _id()
    transaccion_id: Mapped[str] = _fk("transacciones.transaccion_id", index=True)
    producto_id: Mapped[str | None] = _fk("productos.producto_id", nullable=True)
    descripcion: Mapped[str | None] = mapped_column(String(100))
    cantidad: Mapped[Decimal] = mapped_column(Numeric(10, 3))
    precio_unitario: Mapped[Decimal]
    costo_unitario: Mapped[Decimal | None]
    subtotal: Mapped[Decimal]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ CUENTAS POR COBRAR Y POR PAGAR ━━━━━━━━━━━━━━━━━━━━━━


class CuadernoFiado(Base):
    __tablename__ = "cuaderno_fiado"
    __table_args__ = (
        CheckConstraint("monto > 0", name="monto_positivo"),
        Index(None, "empresa_id", "cliente_id"),
    )

    fiado_id: Mapped[str] = _id()
    empresa_id: Mapped[str] = _fk("empresas.empresa_id")
    cliente_id: Mapped[str] = _fk("clientes.cliente_id")
    borrador_id: Mapped[str | None] = _fk("borradores.borrador_id", nullable=True)
    detalle: Mapped[str | None] = mapped_column(String(255))
    monto: Mapped[Decimal]
    fecha_fiado: Mapped[date]
    fecha_compromiso: Mapped[date | None]
    fecha_pago_total: Mapped[date | None]
    canal: Mapped[Canal] = mapped_column(T_CANAL)
    pago_tardio: Mapped[bool | None] = mapped_column(Boolean, comment="ETIQUETA: nunca es feature")


class Deuda(Base):
    __tablename__ = "deudas"
    __table_args__ = (
        CheckConstraint("(tipo = 'proveedor') = (proveedor_id IS NOT NULL)", name="proveedor_segun_tipo"),
        CheckConstraint("monto_recibido > 0", name="monto_recibido_positivo"),
        CheckConstraint("monto_total_a_pagar > 0", name="monto_total_positivo"),
        CheckConstraint("monto_total_a_pagar >= monto_recibido", name="total_mayor_o_igual_recibido"),
        CheckConstraint("monto_cuota IS NULL OR monto_cuota > 0", name="cuota_positiva"),
        CheckConstraint("fecha_vencimiento >= fecha_inicio", name="vencimiento_tras_inicio"),
        Index(None, "empresa_id", "fecha_vencimiento"),
    )

    deuda_id: Mapped[str] = _id()
    empresa_id: Mapped[str] = _fk("empresas.empresa_id")
    tipo: Mapped[TipoDeuda] = mapped_column(T_TIPO_DEUDA)
    proveedor_id: Mapped[str | None] = _fk("proveedores.proveedor_id", nullable=True)
    acreedor_nombre: Mapped[str | None] = mapped_column(String(100))
    borrador_id: Mapped[str | None] = _fk("borradores.borrador_id", nullable=True)
    monto_recibido: Mapped[Decimal]
    monto_total_a_pagar: Mapped[Decimal]
    frecuencia_cuota: Mapped[Frecuencia | None] = mapped_column(T_FRECUENCIA)
    monto_cuota: Mapped[Decimal | None]
    fecha_inicio: Mapped[date]
    fecha_vencimiento: Mapped[date]
    fecha_pago_total: Mapped[date | None]
    canal: Mapped[Canal] = mapped_column(T_CANAL)
    notas: Mapped[str | None] = mapped_column(String(255))


class BilleteraDigital(Base):
    __tablename__ = "billeteras_digitales"
    __table_args__ = (
        CheckConstraint("monto > 0", name="monto_positivo"),
        UniqueConstraint("empresa_id", "proveedor_billetera", "operacion_id"),
    )

    billetera_mov_id: Mapped[str] = _id()
    empresa_id: Mapped[str] = _fk("empresas.empresa_id")
    proveedor_billetera: Mapped[str] = mapped_column(String(30))
    operacion_id: Mapped[str] = mapped_column(String(50))
    tipo: Mapped[TipoFlujo] = mapped_column(T_TIPO_FLUJO)
    monto: Mapped[Decimal]
    contraparte_nombre: Mapped[str | None] = mapped_column(String(100))
    fecha_hora: Mapped[datetime]
    origen: Mapped[OrigenBilletera] = mapped_column(T_ORIGEN_BILLETERA)


class Impuesto(Base):
    __tablename__ = "impuestos"
    __table_args__ = (
        CheckConstraint("monto >= 0", name="monto_no_negativo"),
        CheckConstraint("periodo ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'", name="periodo_aaaa_mm"),
        UniqueConstraint("empresa_id", "regimen", "periodo"),
    )

    impuesto_id: Mapped[str] = _id()
    empresa_id: Mapped[str] = _fk("empresas.empresa_id")
    regimen: Mapped[str] = mapped_column(String(20))
    periodo: Mapped[str] = mapped_column(CHAR(7))
    monto: Mapped[Decimal]
    fecha_vencimiento: Mapped[date]
    fecha_pago: Mapped[date | None]
    canal: Mapped[Canal] = mapped_column(T_CANAL)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ PLANIFICACIÓN ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class MovimientoProgramado(Base):
    __tablename__ = "movimientos_programados"
    __table_args__ = (
        CheckConstraint("monto > 0", name="monto_positivo"),
        CheckConstraint("dia_semana IS NULL OR dia_semana BETWEEN 1 AND 7", name="dia_semana_1_7"),
        CheckConstraint("dia_mes IS NULL OR dia_mes BETWEEN 1 AND 31", name="dia_mes_1_31"),
        CheckConstraint("fecha_fin IS NULL OR fecha_fin >= fecha_inicio", name="fin_tras_inicio"),
        CheckConstraint("NOT es_sueldo OR tipo = 'egreso'", name="sueldo_es_egreso"),
        # Un solo sueldo activo por empresa (índice único parcial del DBML).
        Index(
            "uq_movimientos_programados_sueldo_activo",
            "empresa_id",
            unique=True,
            postgresql_where=text("es_sueldo AND activo"),
        ),
    )

    programado_id: Mapped[str] = _id()
    empresa_id: Mapped[str] = _fk("empresas.empresa_id")
    categoria_id: Mapped[str] = _fk("categorias.categoria_id")
    tipo: Mapped[TipoFlujo] = mapped_column(T_TIPO_FLUJO)
    descripcion: Mapped[str] = mapped_column(String(100))
    monto: Mapped[Decimal]
    frecuencia: Mapped[Frecuencia] = mapped_column(T_FRECUENCIA)
    dia_semana: Mapped[int | None] = mapped_column(SmallInteger)
    dia_mes: Mapped[int | None] = mapped_column(SmallInteger)
    es_sueldo: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    fecha_inicio: Mapped[date]
    fecha_fin: Mapped[date | None]
    activo: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))


class ReglaMeta(Base):
    __tablename__ = "reglas_meta"
    __table_args__ = (CheckConstraint("acumulado >= 0", name="acumulado_no_negativo"),)

    meta_id: Mapped[str] = _id()
    empresa_id: Mapped[str] = _fk("empresas.empresa_id")
    plantilla: Mapped[PlantillaMeta] = mapped_column(T_PLANTILLA_META)
    programado_id: Mapped[str | None] = _fk("movimientos_programados.programado_id", nullable=True)
    tipo_regla: Mapped[TipoRegla | None] = mapped_column(T_TIPO_REGLA)
    valor: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    destino: Mapped[str | None] = mapped_column(String(30))
    objetivo: Mapped[Decimal | None]
    acumulado: Mapped[Decimal] = mapped_column(default=Decimal("0"), server_default=text("0"))
    recordatorio_frecuencia: Mapped[Frecuencia | None] = mapped_column(T_FRECUENCIA)
    recordatorio_dia: Mapped[int | None] = mapped_column(SmallInteger)
    estado: Mapped[EstadoMeta] = mapped_column(T_ESTADO_META, default=EstadoMeta.activa, server_default=text("'activa'"))
    fecha_inicio: Mapped[date]
    fecha_logro: Mapped[date | None]


class ForecastAjuste(Base):
    __tablename__ = "forecast_ajustes"
    __table_args__ = (CheckConstraint("monto >= 0", name="monto_no_negativo"),)

    ajuste_id: Mapped[str] = _id()
    empresa_id: Mapped[str] = _fk("empresas.empresa_id")
    programado_id: Mapped[str | None] = _fk("movimientos_programados.programado_id", nullable=True)
    fecha: Mapped[date]
    concepto: Mapped[str] = mapped_column(String(100))
    monto: Mapped[Decimal]
    motivo: Mapped[str | None] = mapped_column(String(255))
    activo: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    creado_en: Mapped[datetime]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ ALERTAS, CONVERSACIÓN Y CONSENTIMIENTO ━━━━━━━━━━━━━━━


class Alerta(Base):
    __tablename__ = "alertas"
    __table_args__ = (
        CheckConstraint("prioridad BETWEEN 1 AND 8", name="prioridad_1_8"),
        _entre_0_y_1("probabilidad"),
        Index(None, "empresa_id", "estado"),
    )

    alerta_id: Mapped[str] = _id()
    empresa_id: Mapped[str] = _fk("empresas.empresa_id")
    tipo: Mapped[TipoAlerta] = mapped_column(T_TIPO_ALERTA)
    prioridad: Mapped[int] = mapped_column(SmallInteger)
    fecha_evento: Mapped[date]
    monto: Mapped[Decimal | None]
    probabilidad: Mapped[Decimal | None] = mapped_column(PROB)
    nivel_riesgo: Mapped[NivelRiesgo | None] = mapped_column(T_NIVEL_RIESGO)
    causas: Mapped[list | None] = mapped_column(JSON)
    accion_sugerida: Mapped[str | None] = mapped_column(String(50))
    entidad_tipo: Mapped[str | None] = mapped_column(String(30))
    entidad_id: Mapped[str | None] = mapped_column(String(20))
    canal: Mapped[CanalNotificacion] = mapped_column(T_CANAL_NOTIF)
    estado: Mapped[EstadoAlerta] = mapped_column(
        T_ESTADO_ALERTA, default=EstadoAlerta.activa, server_default=text("'activa'")
    )
    accion_tomada: Mapped[str | None] = mapped_column(String(50))
    fecha_accion: Mapped[datetime | None]
    creada_en: Mapped[datetime]
    enviada_en: Mapped[datetime | None]
    modelo_version: Mapped[str | None] = mapped_column(String(30))


class Conversacion(Base):
    __tablename__ = "conversaciones"
    __table_args__ = (Index(None, "empresa_id", "conversacion_id", "fecha_hora"),)

    mensaje_id: Mapped[str] = _id()
    empresa_id: Mapped[str] = _fk("empresas.empresa_id")
    conversacion_id: Mapped[str] = mapped_column(String(20))
    rol: Mapped[RolMensaje] = mapped_column(T_ROL)
    canal: Mapped[CanalNotificacion] = mapped_column(T_CANAL_NOTIF)
    texto: Mapped[str | None] = mapped_column(Text)
    media_url: Mapped[str | None] = mapped_column(String(255))
    intencion: Mapped[str | None] = mapped_column(String(50))
    herramientas_llamadas: Mapped[list | None] = mapped_column(JSON)
    cifras_verificadas: Mapped[bool | None] = mapped_column(Boolean)
    fallback_usado: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    derivado_a_humano: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    prompt_version: Mapped[str | None] = mapped_column(String(30))
    modelo_version: Mapped[str | None] = mapped_column(String(30))
    fecha_hora: Mapped[datetime]


class Consentimiento(Base):
    __tablename__ = "consentimientos"

    consentimiento_id: Mapped[str] = _id()
    empresa_id: Mapped[str] = _fk("empresas.empresa_id")
    alcance: Mapped[list] = mapped_column(JSON)
    activo: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    fecha_otorgado: Mapped[datetime | None]
    vigencia_hasta: Mapped[date | None]
    fecha_revocado: Mapped[datetime | None]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ ETIQUETAS Y RESULTADOS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class SaldoDiario(Base):
    __tablename__ = "saldo_diario"

    empresa_id: Mapped[str] = mapped_column(String(20), ForeignKey("empresas.empresa_id"), primary_key=True)
    fecha: Mapped[date] = mapped_column(primary_key=True)
    saldo_cierre: Mapped[Decimal]
    deficit_14d: Mapped[bool | None] = mapped_column(Boolean, comment="ETIQUETA: nunca es feature")


class Evento(Base):
    """ETIQUETA (toda la tabla): shocks del generador sintético. Nunca es feature."""

    __tablename__ = "eventos"

    evento_id: Mapped[str] = _id()
    empresa_id: Mapped[str] = _fk("empresas.empresa_id")
    tipo_evento: Mapped[TipoEvento] = mapped_column(T_TIPO_EVENTO)
    fecha_inicio: Mapped[date]
    fecha_fin: Mapped[date | None]
    descripcion: Mapped[str | None] = mapped_column(String(255))


class PrediccionSaldo(Base):
    __tablename__ = "predicciones_saldo"
    __table_args__ = (UniqueConstraint("empresa_id", "fecha_corte", "fecha_objetivo", "modelo_version"),)

    prediccion_id: Mapped[str] = _id()
    empresa_id: Mapped[str] = _fk("empresas.empresa_id")
    fecha_corte: Mapped[date]
    fecha_objetivo: Mapped[date]
    p10: Mapped[Decimal]
    p50: Mapped[Decimal]
    p90: Mapped[Decimal]
    modelo_version: Mapped[str] = mapped_column(String(30))
    creado_en: Mapped[datetime]


class PrediccionFiado(Base):
    __tablename__ = "predicciones_fiado"
    __table_args__ = (
        UniqueConstraint("fiado_id", "fecha_corte", "modelo_version"),
        _entre_0_y_1("prob_atraso"),
        _entre_0_y_1("prob_pago_14d"),
    )

    prediccion_id: Mapped[str] = _id()
    fiado_id: Mapped[str] = _fk("cuaderno_fiado.fiado_id")
    fecha_corte: Mapped[date]
    prob_atraso: Mapped[Decimal] = mapped_column(PROB)
    prob_pago_14d: Mapped[Decimal | None] = mapped_column(PROB)
    nivel_riesgo: Mapped[NivelRiesgo] = mapped_column(T_NIVEL_RIESGO)
    modelo_version: Mapped[str] = mapped_column(String(30))
    creado_en: Mapped[datetime]


class ScoreSalud(Base):
    __tablename__ = "score_salud"
    __table_args__ = (
        CheckConstraint("score BETWEEN 0 AND 100", name="score_0_100"),
        CheckConstraint("mes ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'", name="mes_aaaa_mm"),
    )

    empresa_id: Mapped[str] = mapped_column(String(20), ForeignKey("empresas.empresa_id"), primary_key=True)
    mes: Mapped[str] = mapped_column(CHAR(7), primary_key=True)
    score: Mapped[int] = mapped_column(SmallInteger)
    subindicadores: Mapped[dict] = mapped_column(JSON)
    version_formula: Mapped[str] = mapped_column(String(30))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ TÉCNICA ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class IdempotencyKey(Base):
    """Respuesta guardada por Idempotency-Key (no es parte del DBML; contrato §0)."""

    __tablename__ = "idempotency_keys"

    clave: Mapped[str] = mapped_column(String(100), primary_key=True)
    endpoint: Mapped[str] = mapped_column(String(120), primary_key=True)
    empresa_id: Mapped[str | None] = mapped_column(String(20))
    payload_hash: Mapped[str] = mapped_column(String(64))
    status_code: Mapped[int] = mapped_column(Integer)
    respuesta: Mapped[Any] = mapped_column(JSON)
    creado_en: Mapped[datetime]


ORIGENES_LLM = ("extractor", "asistente", "vision")
ESTADOS_LLM = ("ok", "timeout", "http_error", "red", "respuesta_invalida", "sin_configurar")
USOS_LLM = ("aceptada", "rechazada_validacion", "rechazada_verificador")
REFERENCIAS_LLM = ("borrador", "mensaje")


def _en(columna: str, valores: tuple[str, ...], nulo: bool = False) -> str:
    lista = ", ".join(f"'{v}'" for v in valores)
    return f"{columna} IN ({lista})" if not nulo else f"{columna} IS NULL OR {columna} IN ({lista})"


class LlmLlamada(Base):
    """Trazabilidad de cada llamada al LLM/VLM (observabilidad; no es parte del DBML de negocio)."""

    __tablename__ = "llm_llamadas"
    __table_args__ = (
        CheckConstraint(_en("origen", ORIGENES_LLM), name="origen_valido"),
        CheckConstraint(_en("estado", ESTADOS_LLM), name="estado_valido"),
        CheckConstraint(_en("resultado_uso", USOS_LLM, nulo=True), name="resultado_uso_valido"),
        CheckConstraint(_en("referencia_tipo", REFERENCIAS_LLM, nulo=True), name="referencia_tipo_valida"),
        CheckConstraint("prompt_tokens IS NULL OR prompt_tokens >= 0", name="prompt_tokens_no_negativo"),
        CheckConstraint("completion_tokens IS NULL OR completion_tokens >= 0", name="completion_tokens_no_negativo"),
        CheckConstraint("total_tokens IS NULL OR total_tokens >= 0", name="total_tokens_no_negativo"),
        Index(None, "empresa_id", "creado_en"),
        Index(None, "origen", "creado_en"),
    )

    llamada_id: Mapped[str] = _id()
    empresa_id: Mapped[str | None] = _fk("empresas.empresa_id", nullable=True)
    origen: Mapped[str] = mapped_column(String(20))
    referencia_tipo: Mapped[str | None] = mapped_column(String(20))
    referencia_id: Mapped[str | None] = mapped_column(String(20))
    prompt_version: Mapped[str | None] = mapped_column(String(30))
    proveedor: Mapped[str] = mapped_column(String(30), default="openrouter", server_default=text("'openrouter'"))
    modelo_solicitado: Mapped[str | None] = mapped_column(String(100))
    modelo_respondido: Mapped[str | None] = mapped_column(String(100))
    generation_id: Mapped[str | None] = mapped_column(String(100))
    request: Mapped[Any | None] = mapped_column(JSON)
    respuesta: Mapped[Any | None] = mapped_column(JSON)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    completion_tokens: Mapped[int | None] = mapped_column(Integer)
    total_tokens: Mapped[int | None] = mapped_column(Integer)
    costo_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 8))
    latencia_ms: Mapped[int | None] = mapped_column(Integer)
    estado: Mapped[str] = mapped_column(String(20))
    http_status: Mapped[int | None] = mapped_column(SmallInteger)
    error: Mapped[str | None] = mapped_column(Text)
    resultado_uso: Mapped[str | None] = mapped_column(String(30))
    creado_en: Mapped[datetime]


TABLAS_DBML = [
    "rubros", "empresas", "preferencias_alertas", "categorias", "productos", "clientes", "proveedores",
    "borradores", "transacciones", "detalle_transaccion",
    "cuaderno_fiado", "deudas", "billeteras_digitales", "impuestos",
    "movimientos_programados", "reglas_meta", "forecast_ajustes",
    "alertas", "conversaciones", "consentimientos",
    "saldo_diario", "eventos", "predicciones_saldo", "predicciones_fiado", "score_salud",
]  # fmt: skip

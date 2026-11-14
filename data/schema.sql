-- =============================================================================
-- CajaClara — Esquema PostgreSQL Completo (v2)
-- Basado en modelo_datos.dbml y diccionario_datos.md
-- Todos los datos almacenados son sintéticos.
-- =============================================================================

SET timezone = 'America/Lima';

-- Limpieza previa (vistas, tablas y tipos)
DROP VIEW IF EXISTS v_disponible_gastar CASCADE;
DROP VIEW IF EXISTS v_resumen_mes CASCADE;
DROP VIEW IF EXISTS v_impuestos CASCADE;
DROP VIEW IF EXISTS v_deudas CASCADE;
DROP VIEW IF EXISTS v_fiados CASCADE;
DROP VIEW IF EXISTS v_saldo_caja CASCADE;

DROP TABLE IF EXISTS idempotency_keys CASCADE;
DROP TABLE IF EXISTS score_salud CASCADE;
DROP TABLE IF EXISTS predicciones_fiado CASCADE;
DROP TABLE IF EXISTS predicciones_saldo CASCADE;
DROP TABLE IF EXISTS eventos CASCADE;
DROP TABLE IF EXISTS saldo_diario CASCADE;
DROP TABLE IF EXISTS consentimientos CASCADE;
DROP TABLE IF EXISTS alertas CASCADE;
DROP TABLE IF EXISTS forecast_ajustes CASCADE;
DROP TABLE IF EXISTS reglas_meta CASCADE;
DROP TABLE IF EXISTS detalle_transaccion CASCADE;
DROP TABLE IF EXISTS transacciones CASCADE;
DROP TABLE IF EXISTS impuestos CASCADE;
DROP TABLE IF EXISTS billeteras_digitales CASCADE;
DROP TABLE IF EXISTS deudas CASCADE;
DROP TABLE IF EXISTS cuaderno_fiado CASCADE;
DROP TABLE IF EXISTS movimientos_programados CASCADE;
DROP TABLE IF EXISTS borradores CASCADE;
DROP TABLE IF EXISTS conversaciones CASCADE;
DROP TABLE IF EXISTS proveedores CASCADE;
DROP TABLE IF EXISTS clientes CASCADE;
DROP TABLE IF EXISTS productos CASCADE;
DROP TABLE IF EXISTS categorias CASCADE;
DROP TABLE IF EXISTS preferencias_alertas CASCADE;
DROP TABLE IF EXISTS empresas CASCADE;
DROP TABLE IF EXISTS rubros CASCADE;

DROP TYPE IF EXISTS tipo_evento CASCADE;
DROP TYPE IF EXISTS perfil_pago CASCADE;
DROP TYPE IF EXISTS rol_mensaje CASCADE;
DROP TYPE IF EXISTS estado_alerta CASCADE;
DROP TYPE IF EXISTS canal_notificacion CASCADE;
DROP TYPE IF EXISTS nivel_riesgo CASCADE;
DROP TYPE IF EXISTS tipo_alerta CASCADE;
DROP TYPE IF EXISTS estado_meta CASCADE;
DROP TYPE IF EXISTS tipo_regla CASCADE;
DROP TYPE IF EXISTS plantilla_meta CASCADE;
DROP TYPE IF EXISTS origen_billetera CASCADE;
DROP TYPE IF EXISTS frecuencia CASCADE;
DROP TYPE IF EXISTS tipo_deuda CASCADE;
DROP TYPE IF EXISTS estado_borrador CASCADE;
DROP TYPE IF EXISTS origen_monto CASCADE;
DROP TYPE IF EXISTS canal_registro CASCADE;
DROP TYPE IF EXISTS metodo_pago CASCADE;
DROP TYPE IF EXISTS tipo_movimiento CASCADE;
DROP TYPE IF EXISTS tipo_flujo CASCADE;

-- =============================================================================
-- 1. ENUMERACIONES (19 tipos)
-- =============================================================================

CREATE TYPE tipo_flujo AS ENUM ('ingreso', 'egreso');

CREATE TYPE tipo_movimiento AS ENUM (
  'venta',
  'cobro_fiado',
  'prestamo_recibido',
  'otro_ingreso',
  'compra',
  'gasto_negocio',
  'retiro_personal',
  'pago_proveedor',
  'pago_prestamo',
  'pago_impuesto'
);

CREATE TYPE metodo_pago AS ENUM (
  'efectivo',
  'billetera_digital',
  'transferencia',
  'tarjeta',
  'credito'
);

CREATE TYPE canal_registro AS ENUM (
  'voz',
  'texto',
  'foto',
  'billetera_api',
  'manual'
);

CREATE TYPE origen_monto AS ENUM (
  'dicho_por_usuario',
  'catalogo',
  'estimado'
);

CREATE TYPE estado_borrador AS ENUM (
  'pendiente',
  'confirmado',
  'descartado'
);

CREATE TYPE tipo_deuda AS ENUM (
  'proveedor',
  'prestamo_informal',
  'familiar',
  'entidad_financiera'
);

CREATE TYPE frecuencia AS ENUM (
  'diaria',
  'semanal',
  'quincenal',
  'mensual'
);

CREATE TYPE origen_billetera AS ENUM (
  'api',
  'captura'
);

CREATE TYPE plantilla_meta AS ENUM (
  'registrar_30_dias',
  'sueldo_fijo',
  'colchon_caja',
  'apartar_para_pedido',
  'reservar_impuestos'
);

CREATE TYPE tipo_regla AS ENUM (
  'porcentaje_de_venta',
  'monto_fijo'
);

CREATE TYPE estado_meta AS ENUM (
  'activa',
  'lograda',
  'pausada'
);

CREATE TYPE tipo_alerta AS ENUM (
  'faltante_caja',
  'pedido_excesivo',
  'retiro_excesivo',
  'obligacion_proxima',
  'gasto_inusual',
  'caida_ventas',
  'fiado_vencido',
  'meta_lograda',
  'resumen_semanal'
);

CREATE TYPE nivel_riesgo AS ENUM (
  'bajo',
  'medio',
  'alto'
);

CREATE TYPE canal_notificacion AS ENUM (
  'whatsapp',
  'app',
  'email'
);

CREATE TYPE estado_alerta AS ENUM (
  'activa',
  'atendida',
  'descartada'
);

CREATE TYPE rol_mensaje AS ENUM (
  'usuario',
  'asistente'
);

CREATE TYPE perfil_pago AS ENUM (
  'puntual',
  'ocasional',
  'moroso'
);

CREATE TYPE tipo_evento AS ENUM (
  'cliente_no_paga',
  'mes_bajo',
  'alza_proveedor',
  'gasto_extra',
  'retiro_excesivo'
);

-- =============================================================================
-- 2. TABLAS MAESTRAS
-- =============================================================================

CREATE TABLE rubros (
  rubro_id varchar(20) PRIMARY KEY,
  nombre varchar(50) NOT NULL UNIQUE
);

CREATE TABLE empresas (
  empresa_id varchar(20) PRIMARY KEY,
  rubro_id varchar(20) NOT NULL REFERENCES rubros(rubro_id),
  nombre_ficticio varchar(100) NOT NULL,
  telefono_whatsapp varchar(20) NOT NULL UNIQUE,
  zona varchar(50) NOT NULL,
  n_trabajadores smallint NOT NULL DEFAULT 1,
  tiene_ruc boolean NOT NULL DEFAULT false,
  ruc varchar(11) UNIQUE CHECK (ruc IS NULL OR ruc ~ '^10[0-9]{9}$'),
  regimen_tributario varchar(20),
  saldo_inicial decimal(12,2) NOT NULL CHECK (saldo_inicial >= 0),
  fecha_saldo_inicial date NOT NULL,
  minimo_operativo decimal(12,2) NOT NULL CHECK (minimo_operativo >= 0),
  fecha_alta timestamptz NOT NULL
);

CREATE TABLE preferencias_alertas (
  empresa_id varchar(20) PRIMARY KEY REFERENCES empresas(empresa_id),
  canales json NOT NULL,
  max_por_dia smallint NOT NULL DEFAULT 2,
  silencio_desde time NOT NULL DEFAULT '21:00',
  silencio_hasta time NOT NULL DEFAULT '07:00',
  resumen_semanal boolean NOT NULL DEFAULT true
);

CREATE TABLE categorias (
  categoria_id varchar(20) PRIMARY KEY,
  nombre varchar(50) NOT NULL UNIQUE,
  tipo tipo_flujo NOT NULL,
  es_del_negocio boolean NOT NULL DEFAULT true
);

CREATE TABLE productos (
  producto_id varchar(20) PRIMARY KEY,
  empresa_id varchar(20) NOT NULL REFERENCES empresas(empresa_id),
  categoria_id varchar(20) NOT NULL REFERENCES categorias(categoria_id),
  nombre varchar(100) NOT NULL,
  alias json,
  precio_venta decimal(12,2) NOT NULL CHECK (precio_venta > 0),
  costo_unitario decimal(12,2) CHECK (costo_unitario IS NULL OR costo_unitario >= 0),
  activo boolean NOT NULL DEFAULT true
);

CREATE TABLE clientes (
  cliente_id varchar(20) PRIMARY KEY,
  empresa_id varchar(20) NOT NULL REFERENCES empresas(empresa_id),
  nombre_ficticio varchar(100) NOT NULL,
  alias json,
  telefono_ficticio varchar(20),
  perfil_pago perfil_pago,
  creado_en timestamptz NOT NULL
);

CREATE TABLE proveedores (
  proveedor_id varchar(20) PRIMARY KEY,
  empresa_id varchar(20) NOT NULL REFERENCES empresas(empresa_id),
  nombre_ficticio varchar(100) NOT NULL,
  telefono_ficticio varchar(20),
  plazo_pago_dias smallint NOT NULL CHECK (plazo_pago_dias >= 0)
);

-- =============================================================================
-- 3. CONVERSACIONES Y BORRADORES (INGESTA)
-- =============================================================================

CREATE TABLE conversaciones (
  mensaje_id varchar(20) PRIMARY KEY,
  empresa_id varchar(20) NOT NULL REFERENCES empresas(empresa_id),
  conversacion_id varchar(20) NOT NULL,
  rol rol_mensaje NOT NULL,
  canal canal_notificacion NOT NULL,
  texto text,
  media_url varchar(255),
  intencion varchar(50),
  herramientas_llamadas json,
  cifras_verificadas boolean,
  fallback_usado boolean NOT NULL DEFAULT false,
  derivado_a_humano boolean NOT NULL DEFAULT false,
  prompt_version varchar(30),
  modelo_version varchar(30),
  fecha_hora timestamptz NOT NULL
);

CREATE INDEX idx_conversaciones_emp_conv_fecha
  ON conversaciones (empresa_id, conversacion_id, fecha_hora);

CREATE TABLE borradores (
  borrador_id varchar(20) PRIMARY KEY,
  empresa_id varchar(20) NOT NULL REFERENCES empresas(empresa_id),
  mensaje_id varchar(20) REFERENCES conversaciones(mensaje_id),
  canal canal_registro NOT NULL,
  media_url varchar(255),
  texto_original text,
  payload_propuesto json NOT NULL,
  origen_monto origen_monto,
  confianza decimal(4,3) CHECK (confianza IS NULL OR (confianza >= 0 AND confianza <= 1)),
  campos_faltantes json,
  pregunta_aclaratoria text,
  correcciones json,
  estado estado_borrador NOT NULL DEFAULT 'pendiente',
  modelo_version varchar(30),
  prompt_version varchar(30),
  fallback_usado boolean NOT NULL DEFAULT false,
  creado_en timestamptz NOT NULL,
  resuelto_en timestamptz
);

-- =============================================================================
-- 4. PLANIFICACIÓN Y CUENTAS POR COBRAR / PAGAR
-- =============================================================================

CREATE TABLE movimientos_programados (
  programado_id varchar(20) PRIMARY KEY,
  empresa_id varchar(20) NOT NULL REFERENCES empresas(empresa_id),
  categoria_id varchar(20) NOT NULL REFERENCES categorias(categoria_id),
  tipo tipo_flujo NOT NULL,
  descripcion varchar(100) NOT NULL,
  monto decimal(12,2) NOT NULL CHECK (monto > 0),
  frecuencia frecuencia NOT NULL,
  dia_semana smallint CHECK (dia_semana IS NULL OR (dia_semana BETWEEN 1 AND 7)),
  dia_mes smallint CHECK (dia_mes IS NULL OR (dia_mes BETWEEN 1 AND 31)),
  es_sueldo boolean NOT NULL DEFAULT false,
  fecha_inicio date NOT NULL,
  fecha_fin date,
  activo boolean NOT NULL DEFAULT true
);

-- Índice único parcial: un solo sueldo activo por empresa
CREATE UNIQUE INDEX idx_unico_sueldo_activo
  ON movimientos_programados (empresa_id)
  WHERE es_sueldo = true AND activo = true;

CREATE TABLE cuaderno_fiado (
  fiado_id varchar(20) PRIMARY KEY,
  empresa_id varchar(20) NOT NULL REFERENCES empresas(empresa_id),
  cliente_id varchar(20) NOT NULL REFERENCES clientes(cliente_id),
  borrador_id varchar(20) REFERENCES borradores(borrador_id),
  detalle varchar(255),
  monto decimal(12,2) NOT NULL CHECK (monto > 0),
  fecha_fiado date NOT NULL,
  fecha_compromiso date,
  fecha_pago_total date,
  canal canal_registro NOT NULL,
  pago_tardio boolean
);

CREATE INDEX idx_cuaderno_fiado_emp_cli
  ON cuaderno_fiado (empresa_id, cliente_id);

CREATE TABLE deudas (
  deuda_id varchar(20) PRIMARY KEY,
  empresa_id varchar(20) NOT NULL REFERENCES empresas(empresa_id),
  tipo tipo_deuda NOT NULL,
  proveedor_id varchar(20) REFERENCES proveedores(proveedor_id),
  acreedor_nombre varchar(100),
  borrador_id varchar(20) REFERENCES borradores(borrador_id),
  monto_recibido decimal(12,2) NOT NULL CHECK (monto_recibido > 0),
  monto_total_a_pagar decimal(12,2) NOT NULL CHECK (monto_total_a_pagar >= monto_recibido),
  frecuencia_cuota frecuencia,
  monto_cuota decimal(12,2) CHECK (monto_cuota IS NULL OR monto_cuota > 0),
  fecha_inicio date NOT NULL,
  fecha_vencimiento date NOT NULL,
  fecha_pago_total date,
  canal canal_registro NOT NULL,
  notas varchar(255),
  CONSTRAINT chk_deudas_proveedor CHECK ((tipo = 'proveedor') = (proveedor_id IS NOT NULL))
);

CREATE INDEX idx_deudas_emp_vencimiento
  ON deudas (empresa_id, fecha_vencimiento);

CREATE TABLE billeteras_digitales (
  billetera_mov_id varchar(20) PRIMARY KEY,
  empresa_id varchar(20) NOT NULL REFERENCES empresas(empresa_id),
  proveedor_billetera varchar(30) NOT NULL,
  operacion_id varchar(50) NOT NULL,
  tipo tipo_flujo NOT NULL,
  monto decimal(12,2) NOT NULL CHECK (monto > 0),
  contraparte_nombre varchar(100),
  fecha_hora timestamptz NOT NULL,
  origen origen_billetera NOT NULL,
  CONSTRAINT uq_billetera_operacion UNIQUE (empresa_id, proveedor_billetera, operacion_id)
);

CREATE TABLE impuestos (
  impuesto_id varchar(20) PRIMARY KEY,
  empresa_id varchar(20) NOT NULL REFERENCES empresas(empresa_id),
  regimen varchar(20) NOT NULL,
  periodo char(7) NOT NULL,
  monto decimal(12,2) NOT NULL CHECK (monto > 0),
  fecha_vencimiento date NOT NULL,
  fecha_pago date,
  canal canal_registro NOT NULL,
  CONSTRAINT uq_impuestos_emp_reg_per UNIQUE (empresa_id, regimen, periodo)
);

-- =============================================================================
-- 5. TRANSACCIONES Y DETALLE
-- =============================================================================

CREATE TABLE transacciones (
  transaccion_id varchar(20) PRIMARY KEY,
  empresa_id varchar(20) NOT NULL REFERENCES empresas(empresa_id),
  borrador_id varchar(20) REFERENCES borradores(borrador_id),
  fecha_hora timestamptz NOT NULL,
  tipo tipo_movimiento NOT NULL,
  categoria_id varchar(20) NOT NULL REFERENCES categorias(categoria_id),
  descripcion varchar(255),
  monto decimal(12,2) NOT NULL,
  moneda char(3) NOT NULL DEFAULT 'PEN',
  metodo_pago metodo_pago NOT NULL,
  afecta_caja boolean NOT NULL,
  canal canal_registro NOT NULL,
  confianza_extraccion decimal(4,3) CHECK (confianza_extraccion IS NULL OR (confianza_extraccion >= 0 AND confianza_extraccion <= 1)),
  fue_corregida boolean NOT NULL DEFAULT false,
  fiado_id varchar(20) REFERENCES cuaderno_fiado(fiado_id),
  deuda_id varchar(20) REFERENCES deudas(deuda_id),
  impuesto_id varchar(20) UNIQUE REFERENCES impuestos(impuesto_id),
  programado_id varchar(20) REFERENCES movimientos_programados(programado_id),
  billetera_mov_id varchar(20) UNIQUE REFERENCES billeteras_digitales(billetera_mov_id),
  anulada boolean NOT NULL DEFAULT false,
  creado_en timestamptz NOT NULL,

  -- CHECKs formales del diccionario de datos (§2.2)
  CONSTRAINT chk_tx_monto_pos CHECK (monto > 0),
  CONSTRAINT chk_tx_afecta_caja CHECK (afecta_caja = (metodo_pago <> 'credito')),
  CONSTRAINT chk_tx_una_fk_satelite CHECK (
    num_nonnulls(fiado_id, deuda_id, impuesto_id, programado_id) <= 1
  ),
  CONSTRAINT chk_tx_cobro_fiado CHECK (
    tipo <> 'cobro_fiado' OR fiado_id IS NOT NULL
  ),
  CONSTRAINT chk_tx_deuda_obligatoria CHECK (
    tipo NOT IN ('pago_proveedor', 'pago_prestamo', 'prestamo_recibido') OR deuda_id IS NOT NULL
  ),
  CONSTRAINT chk_tx_impuesto_obligatorio CHECK (
    tipo <> 'pago_impuesto' OR impuesto_id IS NOT NULL
  ),
  CONSTRAINT chk_tx_venta_credito CHECK (
    NOT (tipo = 'venta' AND metodo_pago = 'credito') OR fiado_id IS NOT NULL
  ),
  CONSTRAINT chk_tx_compra_credito CHECK (
    NOT (tipo = 'compra' AND metodo_pago = 'credito') OR deuda_id IS NOT NULL
  )
);

CREATE INDEX idx_transacciones_emp_fecha ON transacciones (empresa_id, fecha_hora);
CREATE INDEX idx_transacciones_emp_tipo ON transacciones (empresa_id, tipo);

CREATE TABLE detalle_transaccion (
  detalle_id varchar(20) PRIMARY KEY,
  transaccion_id varchar(20) NOT NULL REFERENCES transacciones(transaccion_id),
  producto_id varchar(20) REFERENCES productos(producto_id),
  descripcion varchar(100),
  cantidad decimal(10,3) NOT NULL CHECK (cantidad > 0),
  precio_unitario decimal(12,2) NOT NULL CHECK (precio_unitario >= 0),
  costo_unitario decimal(12,2) CHECK (costo_unitario IS NULL OR costo_unitario >= 0),
  subtotal decimal(12,2) NOT NULL CHECK (subtotal >= 0)
);

-- =============================================================================
-- 6. METAS, AJUSTES, ALERTAS Y CONSENTIMIENTOS
-- =============================================================================

CREATE TABLE reglas_meta (
  meta_id varchar(20) PRIMARY KEY,
  empresa_id varchar(20) NOT NULL REFERENCES empresas(empresa_id),
  plantilla plantilla_meta NOT NULL,
  programado_id varchar(20) REFERENCES movimientos_programados(programado_id),
  tipo_regla tipo_regla,
  valor decimal(12,4),
  destino varchar(30),
  objetivo decimal(12,2),
  acumulado decimal(12,2) NOT NULL DEFAULT 0,
  recordatorio_frecuencia frecuencia,
  recordatorio_dia smallint,
  estado estado_meta NOT NULL DEFAULT 'activa',
  fecha_inicio date NOT NULL,
  fecha_logro date
);

CREATE TABLE forecast_ajustes (
  ajuste_id varchar(20) PRIMARY KEY,
  empresa_id varchar(20) NOT NULL REFERENCES empresas(empresa_id),
  programado_id varchar(20) REFERENCES movimientos_programados(programado_id),
  fecha date NOT NULL,
  concepto varchar(100) NOT NULL,
  monto decimal(12,2) NOT NULL CHECK (monto >= 0),
  motivo varchar(255),
  activo boolean NOT NULL DEFAULT true,
  creado_en timestamptz NOT NULL
);

CREATE TABLE alertas (
  alerta_id varchar(20) PRIMARY KEY,
  empresa_id varchar(20) NOT NULL REFERENCES empresas(empresa_id),
  tipo tipo_alerta NOT NULL,
  prioridad smallint NOT NULL CHECK (prioridad BETWEEN 1 AND 8),
  fecha_evento date NOT NULL,
  monto decimal(12,2),
  probabilidad decimal(4,3) CHECK (probabilidad IS NULL OR (probabilidad >= 0 AND probabilidad <= 1)),
  nivel_riesgo nivel_riesgo,
  causas json,
  accion_sugerida varchar(50),
  entidad_tipo varchar(30),
  entidad_id varchar(20),
  canal canal_notificacion NOT NULL,
  estado estado_alerta NOT NULL DEFAULT 'activa',
  accion_tomada varchar(50),
  fecha_accion timestamptz,
  creada_en timestamptz NOT NULL,
  enviada_en timestamptz,
  modelo_version varchar(30)
);

CREATE TABLE consentimientos (
  consentimiento_id varchar(20) PRIMARY KEY,
  empresa_id varchar(20) NOT NULL REFERENCES empresas(empresa_id),
  alcance json NOT NULL,
  activo boolean NOT NULL DEFAULT false,
  fecha_otorgado timestamptz,
  vigencia_hasta date,
  fecha_revocado timestamptz
);

-- =============================================================================
-- 7. ETIQUETAS Y RESULTADOS (EVALUACIÓN Y TRAZABILIDAD)
-- =============================================================================

CREATE TABLE saldo_diario (
  empresa_id varchar(20) NOT NULL REFERENCES empresas(empresa_id),
  fecha date NOT NULL,
  saldo_cierre decimal(12,2) NOT NULL,
  deficit_14d boolean,
  PRIMARY KEY (empresa_id, fecha)
);

CREATE TABLE eventos (
  evento_id varchar(20) PRIMARY KEY,
  empresa_id varchar(20) NOT NULL REFERENCES empresas(empresa_id),
  tipo_evento tipo_evento NOT NULL,
  fecha_inicio date NOT NULL,
  fecha_fin date,
  descripcion varchar(255)
);

CREATE TABLE predicciones_saldo (
  prediccion_id varchar(20) PRIMARY KEY,
  empresa_id varchar(20) NOT NULL REFERENCES empresas(empresa_id),
  fecha_corte date NOT NULL,
  fecha_objetivo date NOT NULL,
  p10 decimal(12,2) NOT NULL,
  p50 decimal(12,2) NOT NULL,
  p90 decimal(12,2) NOT NULL,
  modelo_version varchar(30) NOT NULL,
  creado_en timestamptz NOT NULL,
  CONSTRAINT uq_pred_saldo UNIQUE (empresa_id, fecha_corte, fecha_objetivo, modelo_version)
);

CREATE TABLE predicciones_fiado (
  prediccion_id varchar(20) PRIMARY KEY,
  fiado_id varchar(20) NOT NULL REFERENCES cuaderno_fiado(fiado_id),
  fecha_corte date NOT NULL,
  prob_atraso decimal(4,3) NOT NULL CHECK (prob_atraso >= 0 AND prob_atraso <= 1),
  prob_pago_14d decimal(4,3) CHECK (prob_pago_14d IS NULL OR (prob_pago_14d >= 0 AND prob_pago_14d <= 1)),
  nivel_riesgo nivel_riesgo NOT NULL,
  modelo_version varchar(30) NOT NULL,
  creado_en timestamptz NOT NULL,
  CONSTRAINT uq_pred_fiado UNIQUE (fiado_id, fecha_corte, modelo_version)
);

CREATE TABLE score_salud (
  empresa_id varchar(20) NOT NULL REFERENCES empresas(empresa_id),
  mes char(7) NOT NULL,
  score smallint NOT NULL CHECK (score BETWEEN 0 AND 100),
  subindicadores json NOT NULL,
  version_formula varchar(30) NOT NULL,
  PRIMARY KEY (empresa_id, mes)
);

-- Tabla auxiliar opcional para idempotencia de POST en el backend (PLAN_MVP.md)
CREATE TABLE idempotency_keys (
  idempotency_key varchar(100) PRIMARY KEY,
  empresa_id varchar(20) REFERENCES empresas(empresa_id),
  endpoint varchar(100) NOT NULL,
  payload_hash varchar(64) NOT NULL,
  response_status smallint NOT NULL,
  response_body json NOT NULL,
  creado_en timestamptz NOT NULL DEFAULT now()
);

-- =============================================================================
-- 8. VISTAS DERIVADAS (diccionario_datos.md §3, referenciadas a corte 2026-11-14)
-- =============================================================================

-- 8.1 v_saldo_caja: saldo actual de la caja del negocio
CREATE VIEW v_saldo_caja AS
SELECT
  e.empresa_id,
  e.nombre_ficticio,
  e.saldo_inicial,
  e.minimo_operativo,
  e.saldo_inicial + COALESCE(SUM(
    CASE
      WHEN t.tipo IN ('venta', 'cobro_fiado', 'prestamo_recibido', 'otro_ingreso') THEN t.monto
      ELSE -t.monto
    END
  ), 0)::decimal(12,2) AS saldo_actual
FROM empresas e
LEFT JOIN transacciones t
  ON t.empresa_id = e.empresa_id
  AND t.afecta_caja = true
  AND t.anulada = false
GROUP BY e.empresa_id, e.nombre_ficticio, e.saldo_inicial, e.minimo_operativo;

-- 8.2 v_fiados: monto_pendiente, dias_atraso y estado a fecha de corte (2026-11-14)
CREATE VIEW v_fiados AS
SELECT
  f.fiado_id,
  f.empresa_id,
  f.cliente_id,
  c.nombre_ficticio AS cliente,
  f.detalle,
  f.monto,
  f.fecha_fiado,
  f.fecha_compromiso,
  f.fecha_pago_total,
  (f.monto - COALESCE(SUM(t.monto), 0))::decimal(12,2) AS monto_pendiente,
  ('2026-11-14'::date - f.fecha_fiado) AS dias_transcurridos,
  GREATEST(0, '2026-11-14'::date - COALESCE(f.fecha_compromiso, f.fecha_fiado + 15)) AS dias_atraso,
  CASE
    WHEN (f.monto - COALESCE(SUM(t.monto), 0)) <= 0 OR f.fecha_pago_total IS NOT NULL THEN 'pagado'
    WHEN '2026-11-14'::date > COALESCE(f.fecha_compromiso, f.fecha_fiado + 15) THEN 'vencido'
    WHEN (COALESCE(f.fecha_compromiso, f.fecha_fiado + 15) - '2026-11-14'::date) <= 3 THEN 'por_vencer'
    ELSE 'pendiente'
  END AS estado
FROM cuaderno_fiado f
JOIN clientes c ON c.cliente_id = f.cliente_id
LEFT JOIN transacciones t
  ON t.fiado_id = f.fiado_id
  AND t.tipo = 'cobro_fiado'
  AND t.anulada = false
GROUP BY f.fiado_id, c.nombre_ficticio;

-- 8.3 v_deudas: monto_pendiente, dias_para_vencer y estado a fecha de corte (2026-11-14)
CREATE VIEW v_deudas AS
SELECT
  d.deuda_id,
  d.empresa_id,
  d.tipo,
  d.proveedor_id,
  COALESCE(p.nombre_ficticio, d.acreedor_nombre) AS acreedor,
  d.monto_recibido,
  d.monto_total_a_pagar,
  d.frecuencia_cuota,
  d.monto_cuota,
  d.fecha_inicio,
  d.fecha_vencimiento,
  d.fecha_pago_total,
  (d.monto_total_a_pagar - COALESCE(SUM(t.monto), 0))::decimal(12,2) AS monto_pendiente,
  (d.fecha_vencimiento - '2026-11-14'::date) AS dias_para_vencer,
  CASE
    WHEN (d.monto_total_a_pagar - COALESCE(SUM(t.monto), 0)) <= 0 OR d.fecha_pago_total IS NOT NULL THEN 'pagado'
    WHEN d.fecha_vencimiento < '2026-11-14'::date THEN 'vencido'
    WHEN d.tipo = 'proveedor' OR (d.fecha_vencimiento - '2026-11-14'::date) <= 16 THEN 'por_vencer'
    ELSE 'pendiente'
  END AS estado
FROM deudas d
LEFT JOIN proveedores p ON p.proveedor_id = d.proveedor_id
LEFT JOIN transacciones t
  ON t.deuda_id = d.deuda_id
  AND t.tipo IN ('pago_proveedor', 'pago_prestamo')
  AND t.anulada = false
GROUP BY d.deuda_id, p.nombre_ficticio;

-- 8.4 v_impuestos: semáforo al_dia / vencido a fecha de corte (2026-11-14)
CREATE VIEW v_impuestos AS
SELECT
  i.impuesto_id,
  i.empresa_id,
  i.regimen,
  i.periodo,
  i.monto,
  i.fecha_vencimiento,
  i.fecha_pago,
  CASE
    WHEN i.fecha_pago IS NOT NULL THEN 'pagado'
    WHEN i.fecha_vencimiento < '2026-11-14'::date THEN 'vencido'
    ELSE 'al_dia'
  END AS estado
FROM impuestos i;

-- 8.5 v_resumen_mes: resumen mensual de ingresos, egresos y retiros personales
CREATE VIEW v_resumen_mes AS
SELECT
  t.empresa_id,
  to_char(t.fecha_hora AT TIME ZONE 'America/Lima', 'YYYY-MM') AS periodo,
  COALESCE(SUM(CASE WHEN t.tipo IN ('venta', 'cobro_fiado', 'prestamo_recibido', 'otro_ingreso') AND t.afecta_caja THEN t.monto ELSE 0 END), 0)::decimal(12,2) AS ingresos_caja_mes,
  COALESCE(SUM(CASE WHEN t.tipo IN ('compra', 'gasto_negocio', 'retiro_personal', 'pago_proveedor', 'pago_prestamo', 'pago_impuesto') AND t.afecta_caja THEN t.monto ELSE 0 END), 0)::decimal(12,2) AS egresos_caja_mes,
  COALESCE(SUM(CASE WHEN t.tipo = 'retiro_personal' AND t.afecta_caja THEN t.monto ELSE 0 END), 0)::decimal(12,2) AS retiros_personales_mes,
  COALESCE(SUM(CASE WHEN t.tipo = 'venta' THEN t.monto ELSE 0 END), 0)::decimal(12,2) AS ventas_totales_mes
FROM transacciones t
WHERE t.anulada = false
GROUP BY t.empresa_id, to_char(t.fecha_hora AT TIME ZONE 'America/Lima', 'YYYY-MM');

-- 8.6 v_disponible_gastar: disponible para gastar a fecha de corte 2026-11-14
CREATE VIEW v_disponible_gastar AS
SELECT
  sc.empresa_id,
  sc.saldo_actual,
  COALESCE(fc.cobros_esperados, 0)::decimal(12,2) AS cobros_esperados,
  COALESCE(dp.pagos_comprometidos, 0)::decimal(12,2) AS pagos_comprometidos,
  sc.minimo_operativo,
  COALESCE(im.reserva_impuestos, 0)::decimal(12,2) AS reserva_impuestos,
  GREATEST(
    0,
    sc.saldo_actual + COALESCE(fc.cobros_esperados, 0) - COALESCE(dp.pagos_comprometidos, 0) - sc.minimo_operativo - COALESCE(im.reserva_impuestos, 0)
  )::decimal(12,2) AS disponible_para_gastar
FROM v_saldo_caja sc
LEFT JOIN (
  SELECT
    vf.empresa_id,
    ROUND(SUM(vf.monto_pendiente * COALESCE(pf.prob_pago_14d, 0.5)), 2) AS cobros_esperados
  FROM v_fiados vf
  LEFT JOIN predicciones_fiado pf
    ON pf.fiado_id = vf.fiado_id
    AND pf.fecha_corte = '2026-11-14'::date
    AND pf.modelo_version = 'riesgo-atraso-clf-0.2.0'
  WHERE vf.estado <> 'pagado'
  GROUP BY vf.empresa_id
) fc ON fc.empresa_id = sc.empresa_id
LEFT JOIN (
  SELECT
    empresa_id,
    SUM(monto_pendiente) AS pagos_comprometidos
  FROM v_deudas
  WHERE estado <> 'pagado'
  GROUP BY empresa_id
) dp ON dp.empresa_id = sc.empresa_id
LEFT JOIN (
  SELECT
    empresa_id,
    SUM(monto) AS reserva_impuestos
  FROM v_impuestos
  WHERE estado = 'al_dia'
  GROUP BY empresa_id
) im ON im.empresa_id = sc.empresa_id;


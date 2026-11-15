-- TuCaserito — esquema de PostgreSQL GENERADO desde backend/app/db/models.py (no editar a mano).
-- Regenerar:  PYTHONPATH=backend python data/pipeline_python/generar_schema.py
-- Incluye las 27 tablas de models.py (25 del modelo de negocio + idempotency_keys y llm_llamadas).
-- No define vistas: el backend calcula saldo, pendiente, atraso y estados en Python (services/finanzas/consultas.py).
-- Los features v_empresas_flags / v_empresas_credit_features del DBML también se calculan en el backend.

CREATE TYPE tipo_flujo AS ENUM ('ingreso', 'egreso');

CREATE TYPE tipo_movimiento AS ENUM ('venta', 'cobro_fiado', 'prestamo_recibido', 'otro_ingreso', 'compra', 'gasto_negocio', 'retiro_personal', 'pago_proveedor', 'pago_prestamo', 'pago_impuesto');

CREATE TYPE metodo_pago AS ENUM ('efectivo', 'billetera_digital', 'transferencia', 'tarjeta', 'credito');

CREATE TYPE canal_registro AS ENUM ('voz', 'texto', 'foto', 'billetera_api', 'manual');

CREATE TYPE origen_monto AS ENUM ('dicho_por_usuario', 'catalogo', 'estimado');

CREATE TYPE estado_borrador AS ENUM ('pendiente', 'confirmado', 'descartado');

CREATE TYPE tipo_deuda AS ENUM ('proveedor', 'prestamo_informal', 'familiar', 'entidad_financiera');

CREATE TYPE frecuencia AS ENUM ('diaria', 'semanal', 'quincenal', 'mensual');

CREATE TYPE origen_billetera AS ENUM ('api', 'captura');

CREATE TYPE plantilla_meta AS ENUM ('registrar_30_dias', 'sueldo_fijo', 'colchon_caja', 'apartar_para_pedido', 'reservar_impuestos');

CREATE TYPE tipo_regla AS ENUM ('porcentaje_de_venta', 'monto_fijo');

CREATE TYPE estado_meta AS ENUM ('activa', 'lograda', 'pausada');

CREATE TYPE tipo_alerta AS ENUM ('faltante_caja', 'pedido_excesivo', 'retiro_excesivo', 'obligacion_proxima', 'gasto_inusual', 'caida_ventas', 'fiado_vencido', 'meta_lograda', 'resumen_semanal');

CREATE TYPE nivel_riesgo AS ENUM ('bajo', 'medio', 'alto');

CREATE TYPE canal_notificacion AS ENUM ('whatsapp', 'app', 'email');

CREATE TYPE estado_alerta AS ENUM ('activa', 'atendida', 'descartada');

CREATE TYPE rol_mensaje AS ENUM ('usuario', 'asistente');

CREATE TYPE perfil_pago AS ENUM ('puntual', 'ocasional', 'moroso');

CREATE TYPE tipo_evento AS ENUM ('cliente_no_paga', 'mes_bajo', 'alza_proveedor', 'gasto_extra', 'retiro_excesivo');

CREATE TABLE rubros (
    rubro_id VARCHAR(20) NOT NULL, 
    nombre VARCHAR(50) NOT NULL, 
    CONSTRAINT pk_rubros PRIMARY KEY (rubro_id), 
    CONSTRAINT uq_rubros_nombre UNIQUE (nombre)
);

CREATE TABLE categorias (
    categoria_id VARCHAR(20) NOT NULL, 
    nombre VARCHAR(50) NOT NULL, 
    tipo tipo_flujo NOT NULL, 
    es_del_negocio BOOLEAN DEFAULT true NOT NULL, 
    CONSTRAINT pk_categorias PRIMARY KEY (categoria_id), 
    CONSTRAINT uq_categorias_nombre UNIQUE (nombre)
);

CREATE TABLE idempotency_keys (
    clave VARCHAR(100) NOT NULL, 
    endpoint VARCHAR(120) NOT NULL, 
    empresa_id VARCHAR(20), 
    payload_hash VARCHAR(64) NOT NULL, 
    status_code INTEGER NOT NULL, 
    respuesta JSON NOT NULL, 
    creado_en TIMESTAMP WITH TIME ZONE NOT NULL, 
    CONSTRAINT pk_idempotency_keys PRIMARY KEY (clave, endpoint)
);

CREATE TABLE empresas (
    empresa_id VARCHAR(20) NOT NULL, 
    rubro_id VARCHAR(20) NOT NULL, 
    nombre_ficticio VARCHAR(100) NOT NULL, 
    telefono_whatsapp VARCHAR(20) NOT NULL, 
    zona VARCHAR(50) NOT NULL, 
    n_trabajadores SMALLINT DEFAULT 1 NOT NULL, 
    tiene_ruc BOOLEAN DEFAULT false NOT NULL, 
    ruc VARCHAR(11), 
    regimen_tributario VARCHAR(20), 
    saldo_inicial NUMERIC(12, 2) NOT NULL, 
    fecha_saldo_inicial DATE NOT NULL, 
    minimo_operativo NUMERIC(12, 2) NOT NULL, 
    fecha_alta TIMESTAMP WITH TIME ZONE NOT NULL, 
    CONSTRAINT pk_empresas PRIMARY KEY (empresa_id), 
    CONSTRAINT ck_empresas_n_trabajadores_positivo CHECK (n_trabajadores >= 1), 
    CONSTRAINT ck_empresas_minimo_operativo_no_negativo CHECK (minimo_operativo >= 0), 
    CONSTRAINT ck_empresas_saldo_inicial_no_negativo CHECK (saldo_inicial >= 0), 
    CONSTRAINT ck_empresas_ruc_formato CHECK (ruc IS NULL OR ruc ~ '^10[0-9]{9}$'), 
    CONSTRAINT fk_empresas_rubro_id_rubros FOREIGN KEY(rubro_id) REFERENCES rubros (rubro_id), 
    CONSTRAINT uq_empresas_telefono_whatsapp UNIQUE (telefono_whatsapp), 
    CONSTRAINT uq_empresas_ruc UNIQUE (ruc)
);

CREATE TABLE preferencias_alertas (
    empresa_id VARCHAR(20) NOT NULL, 
    canales JSON NOT NULL, 
    max_por_dia SMALLINT DEFAULT 2 NOT NULL, 
    silencio_desde TIME WITHOUT TIME ZONE DEFAULT '21:00' NOT NULL, 
    silencio_hasta TIME WITHOUT TIME ZONE DEFAULT '07:00' NOT NULL, 
    resumen_semanal BOOLEAN DEFAULT true NOT NULL, 
    CONSTRAINT pk_preferencias_alertas PRIMARY KEY (empresa_id), 
    CONSTRAINT ck_preferencias_alertas_max_por_dia_no_negativo CHECK (max_por_dia >= 0), 
    CONSTRAINT fk_preferencias_alertas_empresa_id_empresas FOREIGN KEY(empresa_id) REFERENCES empresas (empresa_id)
);

CREATE TABLE productos (
    producto_id VARCHAR(20) NOT NULL, 
    empresa_id VARCHAR(20) NOT NULL, 
    categoria_id VARCHAR(20) NOT NULL, 
    nombre VARCHAR(100) NOT NULL, 
    alias JSON, 
    precio_venta NUMERIC(12, 2) NOT NULL, 
    costo_unitario NUMERIC(12, 2), 
    activo BOOLEAN DEFAULT true NOT NULL, 
    CONSTRAINT pk_productos PRIMARY KEY (producto_id), 
    CONSTRAINT ck_productos_precio_venta_positivo CHECK (precio_venta > 0), 
    CONSTRAINT ck_productos_costo_no_negativo CHECK (costo_unitario IS NULL OR costo_unitario >= 0), 
    CONSTRAINT fk_productos_empresa_id_empresas FOREIGN KEY(empresa_id) REFERENCES empresas (empresa_id), 
    CONSTRAINT fk_productos_categoria_id_categorias FOREIGN KEY(categoria_id) REFERENCES categorias (categoria_id)
);

CREATE TABLE clientes (
    cliente_id VARCHAR(20) NOT NULL, 
    empresa_id VARCHAR(20) NOT NULL, 
    nombre_ficticio VARCHAR(100) NOT NULL, 
    alias JSON, 
    telefono_ficticio VARCHAR(20), 
    perfil_pago perfil_pago, 
    creado_en TIMESTAMP WITH TIME ZONE NOT NULL, 
    CONSTRAINT pk_clientes PRIMARY KEY (cliente_id), 
    CONSTRAINT fk_clientes_empresa_id_empresas FOREIGN KEY(empresa_id) REFERENCES empresas (empresa_id)
);

COMMENT ON COLUMN clientes.perfil_pago IS 'OCULTO: nunca es feature';

CREATE TABLE proveedores (
    proveedor_id VARCHAR(20) NOT NULL, 
    empresa_id VARCHAR(20) NOT NULL, 
    nombre_ficticio VARCHAR(100) NOT NULL, 
    telefono_ficticio VARCHAR(20), 
    plazo_pago_dias SMALLINT NOT NULL, 
    CONSTRAINT pk_proveedores PRIMARY KEY (proveedor_id), 
    CONSTRAINT ck_proveedores_plazo_no_negativo CHECK (plazo_pago_dias >= 0), 
    CONSTRAINT fk_proveedores_empresa_id_empresas FOREIGN KEY(empresa_id) REFERENCES empresas (empresa_id)
);

CREATE TABLE billeteras_digitales (
    billetera_mov_id VARCHAR(20) NOT NULL, 
    empresa_id VARCHAR(20) NOT NULL, 
    proveedor_billetera VARCHAR(30) NOT NULL, 
    operacion_id VARCHAR(50) NOT NULL, 
    tipo tipo_flujo NOT NULL, 
    monto NUMERIC(12, 2) NOT NULL, 
    contraparte_nombre VARCHAR(100), 
    fecha_hora TIMESTAMP WITH TIME ZONE NOT NULL, 
    origen origen_billetera NOT NULL, 
    CONSTRAINT pk_billeteras_digitales PRIMARY KEY (billetera_mov_id), 
    CONSTRAINT ck_billeteras_digitales_monto_positivo CHECK (monto > 0), 
    CONSTRAINT uq_billeteras_digitales_empresa_id_proveedor_billetera__690c UNIQUE (empresa_id, proveedor_billetera, operacion_id), 
    CONSTRAINT fk_billeteras_digitales_empresa_id_empresas FOREIGN KEY(empresa_id) REFERENCES empresas (empresa_id)
);

CREATE TABLE impuestos (
    impuesto_id VARCHAR(20) NOT NULL, 
    empresa_id VARCHAR(20) NOT NULL, 
    regimen VARCHAR(20) NOT NULL, 
    periodo CHAR(7) NOT NULL, 
    monto NUMERIC(12, 2) NOT NULL, 
    fecha_vencimiento DATE NOT NULL, 
    fecha_pago DATE, 
    canal canal_registro NOT NULL, 
    CONSTRAINT pk_impuestos PRIMARY KEY (impuesto_id), 
    CONSTRAINT ck_impuestos_monto_no_negativo CHECK (monto >= 0), 
    CONSTRAINT ck_impuestos_periodo_aaaa_mm CHECK (periodo ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'), 
    CONSTRAINT uq_impuestos_empresa_id_regimen_periodo UNIQUE (empresa_id, regimen, periodo), 
    CONSTRAINT fk_impuestos_empresa_id_empresas FOREIGN KEY(empresa_id) REFERENCES empresas (empresa_id)
);

CREATE TABLE movimientos_programados (
    programado_id VARCHAR(20) NOT NULL, 
    empresa_id VARCHAR(20) NOT NULL, 
    categoria_id VARCHAR(20) NOT NULL, 
    tipo tipo_flujo NOT NULL, 
    descripcion VARCHAR(100) NOT NULL, 
    monto NUMERIC(12, 2) NOT NULL, 
    frecuencia frecuencia NOT NULL, 
    dia_semana SMALLINT, 
    dia_mes SMALLINT, 
    es_sueldo BOOLEAN DEFAULT false NOT NULL, 
    fecha_inicio DATE NOT NULL, 
    fecha_fin DATE, 
    activo BOOLEAN DEFAULT true NOT NULL, 
    CONSTRAINT pk_movimientos_programados PRIMARY KEY (programado_id), 
    CONSTRAINT ck_movimientos_programados_monto_positivo CHECK (monto > 0), 
    CONSTRAINT ck_movimientos_programados_dia_semana_1_7 CHECK (dia_semana IS NULL OR dia_semana BETWEEN 1 AND 7), 
    CONSTRAINT ck_movimientos_programados_dia_mes_1_31 CHECK (dia_mes IS NULL OR dia_mes BETWEEN 1 AND 31), 
    CONSTRAINT ck_movimientos_programados_fin_tras_inicio CHECK (fecha_fin IS NULL OR fecha_fin >= fecha_inicio), 
    CONSTRAINT ck_movimientos_programados_sueldo_es_egreso CHECK (NOT es_sueldo OR tipo = 'egreso'), 
    CONSTRAINT fk_movimientos_programados_empresa_id_empresas FOREIGN KEY(empresa_id) REFERENCES empresas (empresa_id), 
    CONSTRAINT fk_movimientos_programados_categoria_id_categorias FOREIGN KEY(categoria_id) REFERENCES categorias (categoria_id)
);

CREATE UNIQUE INDEX uq_movimientos_programados_sueldo_activo ON movimientos_programados (empresa_id) WHERE es_sueldo AND activo;

CREATE TABLE alertas (
    alerta_id VARCHAR(20) NOT NULL, 
    empresa_id VARCHAR(20) NOT NULL, 
    tipo tipo_alerta NOT NULL, 
    prioridad SMALLINT NOT NULL, 
    fecha_evento DATE NOT NULL, 
    monto NUMERIC(12, 2), 
    probabilidad NUMERIC(4, 3), 
    nivel_riesgo nivel_riesgo, 
    causas JSON, 
    accion_sugerida VARCHAR(50), 
    entidad_tipo VARCHAR(30), 
    entidad_id VARCHAR(20), 
    canal canal_notificacion NOT NULL, 
    estado estado_alerta DEFAULT 'activa' NOT NULL, 
    accion_tomada VARCHAR(50), 
    fecha_accion TIMESTAMP WITH TIME ZONE, 
    creada_en TIMESTAMP WITH TIME ZONE NOT NULL, 
    enviada_en TIMESTAMP WITH TIME ZONE, 
    modelo_version VARCHAR(30), 
    CONSTRAINT pk_alertas PRIMARY KEY (alerta_id), 
    CONSTRAINT ck_alertas_prioridad_1_8 CHECK (prioridad BETWEEN 1 AND 8), 
    CONSTRAINT ck_alertas_probabilidad_0_1 CHECK (probabilidad IS NULL OR (probabilidad >= 0 AND probabilidad <= 1)), 
    CONSTRAINT fk_alertas_empresa_id_empresas FOREIGN KEY(empresa_id) REFERENCES empresas (empresa_id)
);

CREATE INDEX ix_alertas_empresa_id_estado ON alertas (empresa_id, estado);

CREATE TABLE conversaciones (
    mensaje_id VARCHAR(20) NOT NULL, 
    empresa_id VARCHAR(20) NOT NULL, 
    conversacion_id VARCHAR(20) NOT NULL, 
    rol rol_mensaje NOT NULL, 
    canal canal_notificacion NOT NULL, 
    texto TEXT, 
    media_url VARCHAR(255), 
    intencion VARCHAR(50), 
    herramientas_llamadas JSON, 
    cifras_verificadas BOOLEAN, 
    fallback_usado BOOLEAN DEFAULT false NOT NULL, 
    derivado_a_humano BOOLEAN DEFAULT false NOT NULL, 
    prompt_version VARCHAR(30), 
    modelo_version VARCHAR(30), 
    fecha_hora TIMESTAMP WITH TIME ZONE NOT NULL, 
    CONSTRAINT pk_conversaciones PRIMARY KEY (mensaje_id), 
    CONSTRAINT fk_conversaciones_empresa_id_empresas FOREIGN KEY(empresa_id) REFERENCES empresas (empresa_id)
);

CREATE INDEX ix_conversaciones_empresa_id_conversacion_id_fecha_hora ON conversaciones (empresa_id, conversacion_id, fecha_hora);

CREATE TABLE consentimientos (
    consentimiento_id VARCHAR(20) NOT NULL, 
    empresa_id VARCHAR(20) NOT NULL, 
    alcance JSON NOT NULL, 
    activo BOOLEAN DEFAULT false NOT NULL, 
    fecha_otorgado TIMESTAMP WITH TIME ZONE, 
    vigencia_hasta DATE, 
    fecha_revocado TIMESTAMP WITH TIME ZONE, 
    CONSTRAINT pk_consentimientos PRIMARY KEY (consentimiento_id), 
    CONSTRAINT fk_consentimientos_empresa_id_empresas FOREIGN KEY(empresa_id) REFERENCES empresas (empresa_id)
);

CREATE TABLE saldo_diario (
    empresa_id VARCHAR(20) NOT NULL, 
    fecha DATE NOT NULL, 
    saldo_cierre NUMERIC(12, 2) NOT NULL, 
    deficit_14d BOOLEAN, 
    CONSTRAINT pk_saldo_diario PRIMARY KEY (empresa_id, fecha), 
    CONSTRAINT fk_saldo_diario_empresa_id_empresas FOREIGN KEY(empresa_id) REFERENCES empresas (empresa_id)
);

COMMENT ON COLUMN saldo_diario.deficit_14d IS 'ETIQUETA: nunca es feature';

CREATE TABLE eventos (
    evento_id VARCHAR(20) NOT NULL, 
    empresa_id VARCHAR(20) NOT NULL, 
    tipo_evento tipo_evento NOT NULL, 
    fecha_inicio DATE NOT NULL, 
    fecha_fin DATE, 
    descripcion VARCHAR(255), 
    CONSTRAINT pk_eventos PRIMARY KEY (evento_id), 
    CONSTRAINT fk_eventos_empresa_id_empresas FOREIGN KEY(empresa_id) REFERENCES empresas (empresa_id)
);

CREATE TABLE predicciones_saldo (
    prediccion_id VARCHAR(20) NOT NULL, 
    empresa_id VARCHAR(20) NOT NULL, 
    fecha_corte DATE NOT NULL, 
    fecha_objetivo DATE NOT NULL, 
    p10 NUMERIC(12, 2) NOT NULL, 
    p50 NUMERIC(12, 2) NOT NULL, 
    p90 NUMERIC(12, 2) NOT NULL, 
    modelo_version VARCHAR(30) NOT NULL, 
    creado_en TIMESTAMP WITH TIME ZONE NOT NULL, 
    CONSTRAINT pk_predicciones_saldo PRIMARY KEY (prediccion_id), 
    CONSTRAINT uq_predicciones_saldo_empresa_id_fecha_corte_fecha_obje_d1c1 UNIQUE (empresa_id, fecha_corte, fecha_objetivo, modelo_version), 
    CONSTRAINT fk_predicciones_saldo_empresa_id_empresas FOREIGN KEY(empresa_id) REFERENCES empresas (empresa_id)
);

CREATE TABLE score_salud (
    empresa_id VARCHAR(20) NOT NULL, 
    mes CHAR(7) NOT NULL, 
    score SMALLINT NOT NULL, 
    subindicadores JSON NOT NULL, 
    version_formula VARCHAR(30) NOT NULL, 
    CONSTRAINT pk_score_salud PRIMARY KEY (empresa_id, mes), 
    CONSTRAINT ck_score_salud_score_0_100 CHECK (score BETWEEN 0 AND 100), 
    CONSTRAINT ck_score_salud_mes_aaaa_mm CHECK (mes ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'), 
    CONSTRAINT fk_score_salud_empresa_id_empresas FOREIGN KEY(empresa_id) REFERENCES empresas (empresa_id)
);

CREATE TABLE llm_llamadas (
    llamada_id VARCHAR(20) NOT NULL, 
    empresa_id VARCHAR(20), 
    origen VARCHAR(20) NOT NULL, 
    referencia_tipo VARCHAR(20), 
    referencia_id VARCHAR(20), 
    prompt_version VARCHAR(30), 
    proveedor VARCHAR(30) DEFAULT 'openrouter' NOT NULL, 
    modelo_solicitado VARCHAR(100), 
    modelo_respondido VARCHAR(100), 
    generation_id VARCHAR(100), 
    request JSON, 
    respuesta JSON, 
    prompt_tokens INTEGER, 
    completion_tokens INTEGER, 
    total_tokens INTEGER, 
    costo_usd NUMERIC(12, 8), 
    latencia_ms INTEGER, 
    estado VARCHAR(20) NOT NULL, 
    http_status SMALLINT, 
    error TEXT, 
    resultado_uso VARCHAR(30), 
    creado_en TIMESTAMP WITH TIME ZONE NOT NULL, 
    CONSTRAINT pk_llm_llamadas PRIMARY KEY (llamada_id), 
    CONSTRAINT ck_llm_llamadas_origen_valido CHECK (origen IN ('extractor', 'asistente', 'vision')), 
    CONSTRAINT ck_llm_llamadas_estado_valido CHECK (estado IN ('ok', 'timeout', 'http_error', 'red', 'respuesta_invalida', 'sin_configurar')), 
    CONSTRAINT ck_llm_llamadas_resultado_uso_valido CHECK (resultado_uso IS NULL OR resultado_uso IN ('aceptada', 'rechazada_validacion', 'rechazada_verificador')), 
    CONSTRAINT ck_llm_llamadas_referencia_tipo_valida CHECK (referencia_tipo IS NULL OR referencia_tipo IN ('borrador', 'mensaje')), 
    CONSTRAINT ck_llm_llamadas_prompt_tokens_no_negativo CHECK (prompt_tokens IS NULL OR prompt_tokens >= 0), 
    CONSTRAINT ck_llm_llamadas_completion_tokens_no_negativo CHECK (completion_tokens IS NULL OR completion_tokens >= 0), 
    CONSTRAINT ck_llm_llamadas_total_tokens_no_negativo CHECK (total_tokens IS NULL OR total_tokens >= 0), 
    CONSTRAINT fk_llm_llamadas_empresa_id_empresas FOREIGN KEY(empresa_id) REFERENCES empresas (empresa_id)
);

CREATE INDEX ix_llm_llamadas_empresa_id_creado_en ON llm_llamadas (empresa_id, creado_en);

CREATE INDEX ix_llm_llamadas_origen_creado_en ON llm_llamadas (origen, creado_en);

CREATE TABLE borradores (
    borrador_id VARCHAR(20) NOT NULL, 
    empresa_id VARCHAR(20) NOT NULL, 
    mensaje_id VARCHAR(20), 
    canal canal_registro NOT NULL, 
    media_url VARCHAR(255), 
    texto_original TEXT, 
    payload_propuesto JSON NOT NULL, 
    origen_monto origen_monto, 
    confianza NUMERIC(4, 3), 
    campos_faltantes JSON, 
    pregunta_aclaratoria TEXT, 
    correcciones JSON, 
    estado estado_borrador DEFAULT 'pendiente' NOT NULL, 
    modelo_version VARCHAR(30), 
    prompt_version VARCHAR(30), 
    fallback_usado BOOLEAN DEFAULT false NOT NULL, 
    creado_en TIMESTAMP WITH TIME ZONE NOT NULL, 
    resuelto_en TIMESTAMP WITH TIME ZONE, 
    CONSTRAINT pk_borradores PRIMARY KEY (borrador_id), 
    CONSTRAINT ck_borradores_confianza_0_1 CHECK (confianza IS NULL OR (confianza >= 0 AND confianza <= 1)), 
    CONSTRAINT fk_borradores_empresa_id_empresas FOREIGN KEY(empresa_id) REFERENCES empresas (empresa_id), 
    CONSTRAINT fk_borradores_mensaje_id_conversaciones FOREIGN KEY(mensaje_id) REFERENCES conversaciones (mensaje_id)
);

CREATE TABLE reglas_meta (
    meta_id VARCHAR(20) NOT NULL, 
    empresa_id VARCHAR(20) NOT NULL, 
    plantilla plantilla_meta NOT NULL, 
    programado_id VARCHAR(20), 
    tipo_regla tipo_regla, 
    valor NUMERIC(12, 4), 
    destino VARCHAR(30), 
    objetivo NUMERIC(12, 2), 
    acumulado NUMERIC(12, 2) DEFAULT 0 NOT NULL, 
    recordatorio_frecuencia frecuencia, 
    recordatorio_dia SMALLINT, 
    estado estado_meta DEFAULT 'activa' NOT NULL, 
    fecha_inicio DATE NOT NULL, 
    fecha_logro DATE, 
    CONSTRAINT pk_reglas_meta PRIMARY KEY (meta_id), 
    CONSTRAINT ck_reglas_meta_acumulado_no_negativo CHECK (acumulado >= 0), 
    CONSTRAINT fk_reglas_meta_empresa_id_empresas FOREIGN KEY(empresa_id) REFERENCES empresas (empresa_id), 
    CONSTRAINT fk_reglas_meta_programado_id_movimientos_programados FOREIGN KEY(programado_id) REFERENCES movimientos_programados (programado_id)
);

CREATE TABLE forecast_ajustes (
    ajuste_id VARCHAR(20) NOT NULL, 
    empresa_id VARCHAR(20) NOT NULL, 
    programado_id VARCHAR(20), 
    fecha DATE NOT NULL, 
    concepto VARCHAR(100) NOT NULL, 
    monto NUMERIC(12, 2) NOT NULL, 
    motivo VARCHAR(255), 
    activo BOOLEAN DEFAULT true NOT NULL, 
    creado_en TIMESTAMP WITH TIME ZONE NOT NULL, 
    CONSTRAINT pk_forecast_ajustes PRIMARY KEY (ajuste_id), 
    CONSTRAINT ck_forecast_ajustes_monto_no_negativo CHECK (monto >= 0), 
    CONSTRAINT fk_forecast_ajustes_empresa_id_empresas FOREIGN KEY(empresa_id) REFERENCES empresas (empresa_id), 
    CONSTRAINT fk_forecast_ajustes_programado_id_movimientos_programados FOREIGN KEY(programado_id) REFERENCES movimientos_programados (programado_id)
);

CREATE TABLE cuaderno_fiado (
    fiado_id VARCHAR(20) NOT NULL, 
    empresa_id VARCHAR(20) NOT NULL, 
    cliente_id VARCHAR(20) NOT NULL, 
    borrador_id VARCHAR(20), 
    detalle VARCHAR(255), 
    monto NUMERIC(12, 2) NOT NULL, 
    fecha_fiado DATE NOT NULL, 
    fecha_compromiso DATE, 
    fecha_pago_total DATE, 
    canal canal_registro NOT NULL, 
    pago_tardio BOOLEAN, 
    CONSTRAINT pk_cuaderno_fiado PRIMARY KEY (fiado_id), 
    CONSTRAINT ck_cuaderno_fiado_monto_positivo CHECK (monto > 0), 
    CONSTRAINT fk_cuaderno_fiado_empresa_id_empresas FOREIGN KEY(empresa_id) REFERENCES empresas (empresa_id), 
    CONSTRAINT fk_cuaderno_fiado_cliente_id_clientes FOREIGN KEY(cliente_id) REFERENCES clientes (cliente_id), 
    CONSTRAINT fk_cuaderno_fiado_borrador_id_borradores FOREIGN KEY(borrador_id) REFERENCES borradores (borrador_id)
);

CREATE INDEX ix_cuaderno_fiado_empresa_id_cliente_id ON cuaderno_fiado (empresa_id, cliente_id);

COMMENT ON COLUMN cuaderno_fiado.pago_tardio IS 'ETIQUETA: nunca es feature';

CREATE TABLE deudas (
    deuda_id VARCHAR(20) NOT NULL, 
    empresa_id VARCHAR(20) NOT NULL, 
    tipo tipo_deuda NOT NULL, 
    proveedor_id VARCHAR(20), 
    acreedor_nombre VARCHAR(100), 
    borrador_id VARCHAR(20), 
    monto_recibido NUMERIC(12, 2) NOT NULL, 
    monto_total_a_pagar NUMERIC(12, 2) NOT NULL, 
    frecuencia_cuota frecuencia, 
    monto_cuota NUMERIC(12, 2), 
    fecha_inicio DATE NOT NULL, 
    fecha_vencimiento DATE NOT NULL, 
    fecha_pago_total DATE, 
    canal canal_registro NOT NULL, 
    notas VARCHAR(255), 
    CONSTRAINT pk_deudas PRIMARY KEY (deuda_id), 
    CONSTRAINT ck_deudas_proveedor_segun_tipo CHECK ((tipo = 'proveedor') = (proveedor_id IS NOT NULL)), 
    CONSTRAINT ck_deudas_monto_recibido_positivo CHECK (monto_recibido > 0), 
    CONSTRAINT ck_deudas_monto_total_positivo CHECK (monto_total_a_pagar > 0), 
    CONSTRAINT ck_deudas_total_mayor_o_igual_recibido CHECK (monto_total_a_pagar >= monto_recibido), 
    CONSTRAINT ck_deudas_cuota_positiva CHECK (monto_cuota IS NULL OR monto_cuota > 0), 
    CONSTRAINT ck_deudas_vencimiento_tras_inicio CHECK (fecha_vencimiento >= fecha_inicio), 
    CONSTRAINT fk_deudas_empresa_id_empresas FOREIGN KEY(empresa_id) REFERENCES empresas (empresa_id), 
    CONSTRAINT fk_deudas_proveedor_id_proveedores FOREIGN KEY(proveedor_id) REFERENCES proveedores (proveedor_id), 
    CONSTRAINT fk_deudas_borrador_id_borradores FOREIGN KEY(borrador_id) REFERENCES borradores (borrador_id)
);

CREATE INDEX ix_deudas_empresa_id_fecha_vencimiento ON deudas (empresa_id, fecha_vencimiento);

CREATE TABLE transacciones (
    transaccion_id VARCHAR(20) NOT NULL, 
    empresa_id VARCHAR(20) NOT NULL, 
    borrador_id VARCHAR(20), 
    fecha_hora TIMESTAMP WITH TIME ZONE NOT NULL, 
    tipo tipo_movimiento NOT NULL, 
    categoria_id VARCHAR(20) NOT NULL, 
    descripcion VARCHAR(255), 
    monto NUMERIC(12, 2) NOT NULL, 
    moneda CHAR(3) DEFAULT 'PEN' NOT NULL, 
    metodo_pago metodo_pago NOT NULL, 
    afecta_caja BOOLEAN NOT NULL, 
    canal canal_registro NOT NULL, 
    confianza_extraccion NUMERIC(4, 3), 
    fue_corregida BOOLEAN DEFAULT false NOT NULL, 
    fiado_id VARCHAR(20), 
    deuda_id VARCHAR(20), 
    impuesto_id VARCHAR(20), 
    programado_id VARCHAR(20), 
    billetera_mov_id VARCHAR(20), 
    anulada BOOLEAN DEFAULT false NOT NULL, 
    creado_en TIMESTAMP WITH TIME ZONE NOT NULL, 
    CONSTRAINT pk_transacciones PRIMARY KEY (transaccion_id), 
    CONSTRAINT ck_transacciones_monto_positivo CHECK (monto > 0), 
    CONSTRAINT ck_transacciones_afecta_caja_segun_metodo CHECK (afecta_caja = (metodo_pago <> 'credito')), 
    CONSTRAINT ck_transacciones_un_solo_vinculo CHECK (num_nonnulls(fiado_id, deuda_id, impuesto_id, programado_id) <= 1), 
    CONSTRAINT ck_transacciones_cobro_fiado_con_fiado CHECK (tipo <> 'cobro_fiado' OR fiado_id IS NOT NULL), 
    CONSTRAINT ck_transacciones_pago_o_prestamo_con_deuda CHECK (tipo NOT IN ('pago_proveedor', 'pago_prestamo', 'prestamo_recibido') OR deuda_id IS NOT NULL), 
    CONSTRAINT ck_transacciones_pago_impuesto_con_impuesto CHECK (tipo <> 'pago_impuesto' OR impuesto_id IS NOT NULL), 
    CONSTRAINT ck_transacciones_venta_fiada_con_fiado CHECK (NOT (tipo = 'venta' AND metodo_pago = 'credito') OR fiado_id IS NOT NULL), 
    CONSTRAINT ck_transacciones_compra_credito_con_deuda CHECK (NOT (tipo = 'compra' AND metodo_pago = 'credito') OR deuda_id IS NOT NULL), 
    CONSTRAINT ck_transacciones_moneda_pen CHECK (moneda = 'PEN'), 
    CONSTRAINT ck_transacciones_confianza_extraccion_0_1 CHECK (confianza_extraccion IS NULL OR (confianza_extraccion >= 0 AND confianza_extraccion <= 1)), 
    CONSTRAINT fk_transacciones_empresa_id_empresas FOREIGN KEY(empresa_id) REFERENCES empresas (empresa_id), 
    CONSTRAINT fk_transacciones_borrador_id_borradores FOREIGN KEY(borrador_id) REFERENCES borradores (borrador_id), 
    CONSTRAINT fk_transacciones_categoria_id_categorias FOREIGN KEY(categoria_id) REFERENCES categorias (categoria_id), 
    CONSTRAINT fk_transacciones_fiado_id_cuaderno_fiado FOREIGN KEY(fiado_id) REFERENCES cuaderno_fiado (fiado_id), 
    CONSTRAINT fk_transacciones_deuda_id_deudas FOREIGN KEY(deuda_id) REFERENCES deudas (deuda_id), 
    CONSTRAINT uq_transacciones_impuesto_id UNIQUE (impuesto_id), 
    CONSTRAINT fk_transacciones_impuesto_id_impuestos FOREIGN KEY(impuesto_id) REFERENCES impuestos (impuesto_id), 
    CONSTRAINT fk_transacciones_programado_id_movimientos_programados FOREIGN KEY(programado_id) REFERENCES movimientos_programados (programado_id), 
    CONSTRAINT uq_transacciones_billetera_mov_id UNIQUE (billetera_mov_id), 
    CONSTRAINT fk_transacciones_billetera_mov_id_billeteras_digitales FOREIGN KEY(billetera_mov_id) REFERENCES billeteras_digitales (billetera_mov_id)
);

CREATE INDEX ix_transacciones_empresa_id_fecha_hora ON transacciones (empresa_id, fecha_hora);

CREATE INDEX ix_transacciones_empresa_id_tipo ON transacciones (empresa_id, tipo);

CREATE TABLE predicciones_fiado (
    prediccion_id VARCHAR(20) NOT NULL, 
    fiado_id VARCHAR(20) NOT NULL, 
    fecha_corte DATE NOT NULL, 
    prob_atraso NUMERIC(4, 3) NOT NULL, 
    prob_pago_14d NUMERIC(4, 3), 
    nivel_riesgo nivel_riesgo NOT NULL, 
    modelo_version VARCHAR(30) NOT NULL, 
    creado_en TIMESTAMP WITH TIME ZONE NOT NULL, 
    CONSTRAINT pk_predicciones_fiado PRIMARY KEY (prediccion_id), 
    CONSTRAINT uq_predicciones_fiado_fiado_id_fecha_corte_modelo_version UNIQUE (fiado_id, fecha_corte, modelo_version), 
    CONSTRAINT ck_predicciones_fiado_prob_atraso_0_1 CHECK (prob_atraso IS NULL OR (prob_atraso >= 0 AND prob_atraso <= 1)), 
    CONSTRAINT ck_predicciones_fiado_prob_pago_14d_0_1 CHECK (prob_pago_14d IS NULL OR (prob_pago_14d >= 0 AND prob_pago_14d <= 1)), 
    CONSTRAINT fk_predicciones_fiado_fiado_id_cuaderno_fiado FOREIGN KEY(fiado_id) REFERENCES cuaderno_fiado (fiado_id)
);

CREATE TABLE detalle_transaccion (
    detalle_id VARCHAR(20) NOT NULL, 
    transaccion_id VARCHAR(20) NOT NULL, 
    producto_id VARCHAR(20), 
    descripcion VARCHAR(100), 
    cantidad NUMERIC(10, 3) NOT NULL, 
    precio_unitario NUMERIC(12, 2) NOT NULL, 
    costo_unitario NUMERIC(12, 2), 
    subtotal NUMERIC(12, 2) NOT NULL, 
    CONSTRAINT pk_detalle_transaccion PRIMARY KEY (detalle_id), 
    CONSTRAINT ck_detalle_transaccion_cantidad_positiva CHECK (cantidad > 0), 
    CONSTRAINT ck_detalle_transaccion_precio_no_negativo CHECK (precio_unitario >= 0), 
    CONSTRAINT ck_detalle_transaccion_subtotal_no_negativo CHECK (subtotal >= 0), 
    CONSTRAINT ck_detalle_transaccion_costo_no_negativo CHECK (costo_unitario IS NULL OR costo_unitario >= 0), 
    CONSTRAINT fk_detalle_transaccion_transaccion_id_transacciones FOREIGN KEY(transaccion_id) REFERENCES transacciones (transaccion_id), 
    CONSTRAINT fk_detalle_transaccion_producto_id_productos FOREIGN KEY(producto_id) REFERENCES productos (producto_id)
);

CREATE INDEX ix_detalle_transaccion_transaccion_id ON detalle_transaccion (transaccion_id);

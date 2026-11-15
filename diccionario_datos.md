# TuCaserito — Diccionario de datos (v2)

> Esquema formal: [modelo_datos.dbml](modelo_datos.dbml) (se visualiza pegándolo en <https://dbdiagram.io>).
> Todos los datos son **sintéticos**. Ningún nombre, teléfono, monto ni negocio corresponde a una persona real.

---

## 0. Convenciones

| Convención | Regla |
|---|---|
| Identificadores | `varchar(20)` con prefijo legible, igual que en [contract.md](contract.md): `EMP-0001`, `MOV-000123`, `BOR-7781`, `AJU-0003`. |
| Montos | `decimal(12,2)` en soles (`PEN`). Siempre positivos; el signo lo da el tipo de movimiento. Nunca `float`. |
| Fechas | `date` para días; `timestamptz` para fecha y hora, zona `America/Lima`. |
| Probabilidades y confianzas | `decimal(4,3)` entre 0 y 1. |
| Borrado | No se borra nada transaccional: se marca `anulada = true` (trazabilidad). |
| Campos calculados | Saldo, monto pendiente, días de atraso y estados *por vencer / vencido / al día* **no se guardan**: salen de vistas (§3), calculadas a una fecha de corte. |
| Columna **Uso ML** | `feature` = puede entrar a un modelo (solo con datos anteriores a `fecha_corte`) · `etiqueta` = target o ground truth, **nunca feature** · `prohibido` = oculto, solo lo usa el generador · `—` = operativo o trazabilidad. |

---

## 1. Enumeraciones

| Enum | Valores | Notas |
|---|---|---|
| `tipo_flujo` | `ingreso`, `egreso` | |
| `tipo_movimiento` | **Ingresos:** `venta`, `cobro_fiado`, `prestamo_recibido`, `otro_ingreso` · **Egresos:** `compra`, `gasto_negocio`, `retiro_personal`, `pago_proveedor`, `pago_prestamo`, `pago_impuesto` | El signo en el saldo sale del grupo. |
| `metodo_pago` | `efectivo`, `billetera_digital`, `transferencia`, `tarjeta`, `credito` | `credito` = fiado (venta) o pedido a crédito (compra): **no mueve caja**. |
| `canal_registro` | `voz`, `texto`, `foto`, `billetera_api`, `manual` | `manual` = formulario web. |
| `origen_monto` | `dicho_por_usuario`, `catalogo`, `estimado` | Cómo se obtuvo el monto del borrador. |
| `estado_borrador` | `pendiente`, `confirmado`, `descartado` | |
| `tipo_deuda` | `proveedor`, `prestamo_informal`, `familiar`, `entidad_financiera` | |
| `frecuencia` | `diaria`, `semanal`, `quincenal`, `mensual` | |
| `origen_billetera` | `api`, `captura` | |
| `plantilla_meta` | `registrar_30_dias`, `sueldo_fijo`, `colchon_caja`, `apartar_para_pedido`, `reservar_impuestos` | |
| `tipo_regla` | `porcentaje_de_venta`, `monto_fijo` | |
| `estado_meta` | `activa`, `lograda`, `pausada` | |
| `tipo_alerta` | `faltante_caja`, `pedido_excesivo`, `retiro_excesivo`, `obligacion_proxima`, `gasto_inusual`, `caida_ventas`, `fiado_vencido`, `meta_lograda`, `resumen_semanal` | Prioridad 1 a 8 según F6. |
| `nivel_riesgo` | `bajo`, `medio`, `alto` | |
| `canal_notificacion` | `whatsapp`, `app`, `email` | |
| `estado_alerta` | `activa`, `atendida`, `descartada` | |
| `rol_mensaje` | `usuario`, `asistente` | |
| `perfil_pago` | `puntual`, `ocasional`, `moroso` | **Prohibido** como feature. |
| `tipo_evento` | `cliente_no_paga`, `mes_bajo`, `alza_proveedor`, `gasto_extra`, `retiro_excesivo` | Shocks del generador. |

---

## 2. Tablas

### 2.1 Maestras

#### `rubros`
Catálogo de rubros. **Grano:** un rubro.

| Campo | Tipo | Nulo | Descripción | Ejemplo | Uso ML |
|---|---|---|---|---|---|
| `rubro_id` | varchar(20) | PK | Identificador | `RUB-01` | — |
| `nombre` | varchar(50) | no | Nombre único del rubro | `bodega` | feature |

#### `empresas`
La pyme ficticia; entidad central. **Grano:** una empresa.

| Campo | Tipo | Nulo | Descripción | Ejemplo | Uso ML |
|---|---|---|---|---|---|
| `empresa_id` | varchar(20) | PK | Identificador | `EMP-0001` | — |
| `rubro_id` | varchar(20) | no | FK → `rubros` | `RUB-01` | feature |
| `nombre_ficticio` | varchar(100) | no | Nombre del negocio | `Bodega Don Pedro` | — |
| `telefono_whatsapp` | varchar(20) | no, único | Teléfono ficticio; enruta los mensajes del webhook | `+51900000001` | — |
| `zona` | varchar(50) | no | Distrito o zona (comparación con pares) | `SJL` | feature |
| `n_trabajadores` | smallint | no | Personas que atienden | `1` | feature |
| `tiene_ruc` | boolean | no | Si ya se formalizó (Estadio 3) | `false` | — |
| `regimen_tributario` | varchar(20) | sí | Régimen si tiene RUC | `nuevo_rus` | — |
| `saldo_inicial` | decimal(12,2) | no | Caja del negocio al empezar a registrar | `1800.00` | — |
| `fecha_saldo_inicial` | date | no | Fecha de ese saldo | `2026-05-01` | — |
| `minimo_operativo` | decimal(12,2) | no | Saldo mínimo para operar sin riesgo | `500.00` | feature |
| `fecha_alta` | timestamptz | no | Alta en TuCaserito | | — |

> El sueldo fijo **no** está aquí: es un `movimientos_programados` con `es_sueldo = true`.

#### `preferencias_alertas`
Preferencias de notificación (contrato §6.4). **Grano:** una por empresa (1─1).

| Campo | Tipo | Nulo | Descripción | Ejemplo |
|---|---|---|---|---|
| `empresa_id` | varchar(20) | PK, FK | Empresa | `EMP-0001` |
| `canales` | json | no | Canales activos | `["whatsapp"]` |
| `max_por_dia` | smallint | no | Tope de alertas diarias (def. 2) | `2` |
| `silencio_desde` | time | no | Inicio del horario silencioso | `21:00` |
| `silencio_hasta` | time | no | Fin del horario silencioso | `07:00` |
| `resumen_semanal` | boolean | no | Enviar resumen semanal | `true` |

#### `categorias`
Categorías globales de ingreso y egreso. **Grano:** una categoría.

| Campo | Tipo | Nulo | Descripción | Ejemplo | Uso ML |
|---|---|---|---|---|---|
| `categoria_id` | varchar(20) | PK | Identificador | `CAT-07` | — |
| `nombre` | varchar(50) | no, único | Nombre | `bebidas`, `servicios`, `retiro personal` | feature |
| `tipo` | tipo_flujo | no | Ingreso o egreso | `egreso` | feature |
| `es_del_negocio` | boolean | no | `false` para retiro personal: no cuenta como gasto del negocio en la ganancia | `true` | — |

> **Alcance:** no existen categorías de gastos del hogar (comida, colegio, salud, servicios de la vivienda). Lo único personal que se registra es el retiro personal desde la caja del negocio ([context.md](context.md), §3 "Alcance").

#### `productos`
Catálogo de cada empresa. **Grano:** un producto de una empresa.

| Campo | Tipo | Nulo | Descripción | Ejemplo | Uso ML |
|---|---|---|---|---|---|
| `producto_id` | varchar(20) | PK | Identificador | `PRD-0031` | — |
| `empresa_id` | varchar(20) | no | FK → `empresas` | | — |
| `categoria_id` | varchar(20) | no | FK → `categorias` | `CAT-01` | feature |
| `nombre` | varchar(100) | no | Nombre del producto | `Cerveza 620 ml` | — |
| `alias` | json | sí | Formas de nombrarlo (ayuda al extractor) | `["chela", "cerveza grande"]` | — |
| `precio_venta` | decimal(12,2) | no | Precio actual | `6.50` | feature |
| `costo_unitario` | decimal(12,2) | sí | Costo actual; null → la ganancia se muestra como rango | `4.80` | feature |
| `activo` | boolean | no | Si sigue a la venta | `true` | — |

#### `clientes`
Vecinos y clientes de fiado. **Grano:** un cliente de una empresa.

| Campo | Tipo | Nulo | Descripción | Ejemplo | Uso ML |
|---|---|---|---|---|---|
| `cliente_id` | varchar(20) | PK | Identificador | `CLI-0012` | — |
| `empresa_id` | varchar(20) | no | FK → `empresas` | | — |
| `nombre_ficticio` | varchar(100) | no | Cómo lo llama el dueño | `Sra. Carmen` | — |
| `alias` | json | sí | Variantes para emparejar voz u OCR | `["carmen", "la señora carmen"]` | — |
| `telefono_ficticio` | varchar(20) | sí | Para el recordatorio de un toque | `+51900000123` | — |
| `perfil_pago` | perfil_pago | sí | Comportamiento simulado por el generador | `ocasional` | **prohibido** |
| `creado_en` | timestamptz | no | Alta del cliente | | — |

#### `proveedores`
**Grano:** un proveedor de una empresa.

| Campo | Tipo | Nulo | Descripción | Ejemplo | Uso ML |
|---|---|---|---|---|---|
| `proveedor_id` | varchar(20) | PK | Identificador | `PRV-0003` | — |
| `empresa_id` | varchar(20) | no | FK → `empresas` | | — |
| `nombre_ficticio` | varchar(100) | no | Nombre | `Distribuidora Andina` | — |
| `telefono_ficticio` | varchar(20) | sí | Contacto ficticio | | — |
| `plazo_pago_dias` | smallint | no | Plazo habitual que da el proveedor | `15` | feature |

---

### 2.2 Ingesta y transacciones

#### `borradores`
Lo que entendió la IA antes de que el usuario confirme (contrato §1.2–1.4). **Grano:** un intento de registro.

| Campo | Tipo | Nulo | Descripción | Ejemplo |
|---|---|---|---|---|
| `borrador_id` | varchar(20) | PK | Identificador | `BOR-7781` |
| `empresa_id` | varchar(20) | no | FK → `empresas` | |
| `mensaje_id` | varchar(20) | sí | FK → `conversaciones`: mensaje que lo originó (null si es formulario) | |
| `canal` | canal_registro | no | Canal de entrada | `voz` |
| `media_url` | varchar(255) | sí | Audio o foto | `file://data/audios/demo_001.ogg` |
| `texto_original` | text | sí | Texto escrito o transcripción de Whisper | `vendí dos cervezas` |
| `payload_propuesto` | json | no | Movimiento(s) propuesto(s); una foto del cuaderno puede traer varios fiados | |
| `origen_monto` | origen_monto | sí | De dónde salió el monto | `catalogo` |
| `confianza` | decimal(4,3) | sí | Confianza global de la extracción | `0.930` |
| `campos_faltantes` | json | sí | Campos que no se pudieron extraer | `["metodo_pago"]` |
| `pregunta_aclaratoria` | text | sí | Repregunta enviada (si confianza < 0.75 o faltan campos) | `¿Fue en efectivo o por billetera?` |
| `correcciones` | json | sí | Lo que corrigió el usuario | `{"metodo_pago": "billetera_digital"}` |
| `estado` | estado_borrador | no | Ciclo de vida | `confirmado` |
| `modelo_version` | varchar(30) | sí | Versión de Whisper + extractor | `0.2.0` |
| `prompt_version` | varchar(30) | sí | Versión del prompt | `extractor-v3` |
| `fallback_usado` | boolean | no | Si se usó la extracción por reglas | `false` |
| `creado_en` | timestamptz | no | | |
| `resuelto_en` | timestamptz | sí | Cuándo se confirmó o descartó | |

> Base de las métricas de F1: WER (`texto_original` vs transcripción de referencia), exactitud por campo (`payload_propuesto` vs verdad) y % de registros corregidos (`correcciones` no vacío).

#### `transacciones`
Todo movimiento de dinero (y las ventas o compras a crédito, que no mueven caja). **Grano:** un movimiento.

| Campo | Tipo | Nulo | Descripción | Ejemplo | Uso ML |
|---|---|---|---|---|---|
| `transaccion_id` | varchar(20) | PK | Identificador | `MOV-000123` | — |
| `empresa_id` | varchar(20) | no | FK → `empresas` | | — |
| `borrador_id` | varchar(20) | sí | FK → `borradores` (null si es formulario o API) | `BOR-7781` | — |
| `fecha_hora` | timestamptz | no | Cuándo ocurrió | `2026-11-14T10:42:00-05:00` | feature |
| `tipo` | tipo_movimiento | no | Qué pasó | `venta` | feature |
| `categoria_id` | varchar(20) | no | FK → `categorias` | `CAT-01` | feature |
| `descripcion` | varchar(255) | sí | Texto libre | `2 cervezas` | — |
| `monto` | decimal(12,2) | no | Monto positivo | `13.00` | feature |
| `moneda` | char(3) | no | Siempre `PEN` | `PEN` | — |
| `metodo_pago` | metodo_pago | no | Cómo se pagó | `efectivo` | feature |
| `afecta_caja` | boolean | no | `false` si `metodo_pago = credito` | `true` | — |
| `canal` | canal_registro | no | Cómo se registró | `voz` | — |
| `confianza_extraccion` | decimal(4,3) | sí | Copia de la confianza del borrador | `0.930` | — |
| `fue_corregida` | boolean | no | Si el usuario corrigió algo al confirmar | `false` | — |
| `fiado_id` | varchar(20) | sí | FK → `cuaderno_fiado` (venta fiada o cobro de fiado) | | — |
| `deuda_id` | varchar(20) | sí | FK → `deudas` (pedido a crédito, préstamo recibido o pago de cuota) | | — |
| `impuesto_id` | varchar(20) | sí, único | FK → `impuestos` (1─1) | | — |
| `programado_id` | varchar(20) | sí | FK → `movimientos_programados` (pago de un recurrente o del sueldo) | | — |
| `billetera_mov_id` | varchar(20) | sí, único | FK → `billeteras_digitales` (1─1) | | — |
| `anulada` | boolean | no | Anulada en vez de borrada | `false` | — |
| `creado_en` | timestamptz | no | Cuándo se guardó (puede ser después de `fecha_hora`) | | — |

**Restricciones (CHECK):**
- `monto > 0` y `afecta_caja = (metodo_pago <> 'credito')`.
- A lo más una de `fiado_id`, `deuda_id`, `impuesto_id`, `programado_id`.
- `cobro_fiado` → `fiado_id` obligatorio · `pago_proveedor`, `pago_prestamo`, `prestamo_recibido` → `deuda_id` obligatorio · `pago_impuesto` → `impuesto_id` obligatorio.
- `venta` + `credito` → `fiado_id` obligatorio · `compra` + `credito` → `deuda_id` obligatorio.

> **Fuga de datos:** para entrenar, filtra por `creado_en < fecha_corte`, no solo por `fecha_hora`. Un fiado registrado hoy por foto con fecha de hace un mes no existía en la fecha de corte.

#### `detalle_transaccion`
Ítems de una venta o compra. **Grano:** un producto dentro de una transacción.

| Campo | Tipo | Nulo | Descripción | Ejemplo | Uso ML |
|---|---|---|---|---|---|
| `detalle_id` | varchar(20) | PK | Identificador | | — |
| `transaccion_id` | varchar(20) | no | FK → `transacciones` | `MOV-000123` | — |
| `producto_id` | varchar(20) | sí | FK → `productos` (null si no está en el catálogo) | `PRD-0031` | feature |
| `descripcion` | varchar(100) | sí | Texto libre si no hay producto | | — |
| `cantidad` | decimal(10,3) | no | Unidades (admite kilos) | `2` | feature |
| `precio_unitario` | decimal(12,2) | no | Precio cobrado | `6.50` | feature |
| `costo_unitario` | decimal(12,2) | sí | Costo copiado al momento de la venta (margen histórico) | `4.80` | feature |
| `subtotal` | decimal(12,2) | no | `cantidad × precio_unitario` | `13.00` | — |

---

### 2.3 Cuentas por cobrar y por pagar

#### `cuaderno_fiado`
Fiados digitalizados. **Grano:** un fiado (puede pagarse en varias partes).

| Campo | Tipo | Nulo | Descripción | Ejemplo | Uso ML |
|---|---|---|---|---|---|
| `fiado_id` | varchar(20) | PK | Identificador | `FIA-0045` | — |
| `empresa_id` | varchar(20) | no | FK → `empresas` | | — |
| `cliente_id` | varchar(20) | no | FK → `clientes` | `CLI-0012` | feature (historial del cliente) |
| `borrador_id` | varchar(20) | sí | FK → `borradores` | | — |
| `detalle` | varchar(255) | sí | Qué se llevó | `2 panes, 1 leche` | — |
| `monto` | decimal(12,2) | no | Monto fiado | `120.00` | feature |
| `fecha_fiado` | date | no | Cuándo se fió | `2026-10-27` | feature |
| `fecha_compromiso` | date | sí | Cuándo prometió pagar | `2026-11-05` | feature |
| `fecha_pago_total` | date | sí | Cuándo terminó de pagar | | solo si `< fecha_corte` |
| `canal` | canal_registro | no | Cómo se registró | `foto` | — |
| `pago_tardio` | boolean | sí | Pagó después del compromiso o del umbral | `true` | **etiqueta** |

> `monto_pendiente` y `dias_atraso` salen de `v_fiados` (§3). Guardar `dias_atraso` causaría fuga: depende de `fecha_pago_total`, que es futura respecto a la fecha de corte.

#### `deudas`
Lo que el negocio debe: pedidos de mercadería a crédito **y** préstamos de dinero (gota a gota, familiar, entidad). **Grano:** una deuda.

| Campo | Tipo | Nulo | Descripción | Ejemplo | Uso ML |
|---|---|---|---|---|---|
| `deuda_id` | varchar(20) | PK | Identificador | `DEU-0009` | — |
| `empresa_id` | varchar(20) | no | FK → `empresas` | | — |
| `tipo` | tipo_deuda | no | Clase de deuda | `proveedor` | feature |
| `proveedor_id` | varchar(20) | sí | FK → `proveedores`; obligatorio si `tipo = proveedor` | `PRV-0003` | — |
| `acreedor_nombre` | varchar(100) | sí | A quién se le debe, si no es proveedor | `prestamista` | — |
| `borrador_id` | varchar(20) | sí | FK → `borradores` | | — |
| `monto_recibido` | decimal(12,2) | no | Dinero recibido o mercadería valorizada | `1000.00` | feature |
| `monto_total_a_pagar` | decimal(12,2) | no | Lo que se devolverá, con intereses | `1200.00` | feature |
| `frecuencia_cuota` | frecuencia | sí | Frecuencia de cuotas (null = un solo pago) | `diaria` | feature |
| `monto_cuota` | decimal(12,2) | sí | Monto de cada cuota | `40.00` | feature |
| `fecha_inicio` | date | no | Fecha del pedido o del préstamo | `2026-11-01` | feature |
| `fecha_vencimiento` | date | no | Último pago pactado | `2026-11-30` | feature |
| `fecha_pago_total` | date | sí | Cuándo se terminó de pagar | | solo si `< fecha_corte` |
| `canal` | canal_registro | no | Cómo se registró | `voz` | — |
| `notas` | varchar(255) | sí | | | — |

> Costo del préstamo informal (F7): `monto_total_a_pagar − monto_recibido` sobre el plazo. `monto_pendiente` y `estado` salen de `v_deudas`.

#### `billeteras_digitales`
Movimientos digitales normalizados (F1.3, roadmap; en la demo, sintéticos). **Grano:** una operación del proveedor.

| Campo | Tipo | Nulo | Descripción | Ejemplo |
|---|---|---|---|---|
| `billetera_mov_id` | varchar(20) | PK | Identificador | `BIL-0201` |
| `empresa_id` | varchar(20) | no | FK → `empresas` | |
| `proveedor_billetera` | varchar(30) | no | Billetera (nombre genérico) | `billetera_a` |
| `operacion_id` | varchar(50) | no | ID de la operación del proveedor | `OP-88123` |
| `tipo` | tipo_flujo | no | Ingreso o egreso | `ingreso` |
| `monto` | decimal(12,2) | no | Monto | `25.00` |
| `contraparte_nombre` | varchar(100) | sí | Nombre ficticio del que paga o cobra | |
| `fecha_hora` | timestamptz | no | | |
| `origen` | origen_billetera | no | API o captura de pantalla | `api` |

> Único `(empresa_id, proveedor_billetera, operacion_id)` para no duplicar. Cada operación genera una `transacciones` con su tipo real (p. ej. `venta` + `billetera_digital`).

#### `impuestos`
Obligaciones tributarias (F1.4). **Grano:** un periodo de un régimen.

| Campo | Tipo | Nulo | Descripción | Ejemplo | Uso ML |
|---|---|---|---|---|---|
| `impuesto_id` | varchar(20) | PK | Identificador | `IMP-0010` | — |
| `empresa_id` | varchar(20) | no | FK → `empresas` | | — |
| `regimen` | varchar(20) | no | Régimen | `nuevo_rus` | — |
| `periodo` | char(7) | no | `AAAA-MM` | `2026-10` | — |
| `monto` | decimal(12,2) | no | Monto a pagar | `20.00` | feature |
| `fecha_vencimiento` | date | no | Vencimiento | `2026-11-18` | feature |
| `fecha_pago` | date | sí | Cuándo se pagó | | solo si `< fecha_corte` |
| `canal` | canal_registro | no | Cómo se registró | `texto` | — |

> Único `(empresa_id, regimen, periodo)`. El semáforo *al día / vencido* sale de `v_impuestos`.

---

### 2.4 Planificación

#### `movimientos_programados`
Ingresos y egresos recurrentes, **incluido el sueldo fijo del dueño**. **Grano:** una regla de recurrencia vigente en un rango de fechas.

| Campo | Tipo | Nulo | Descripción | Ejemplo |
|---|---|---|---|---|
| `programado_id` | varchar(20) | PK | Identificador | `PRG-0004` |
| `empresa_id` | varchar(20) | no | FK → `empresas` | |
| `categoria_id` | varchar(20) | no | FK → `categorias` | `servicios` |
| `tipo` | tipo_flujo | no | Ingreso o egreso | `egreso` |
| `descripcion` | varchar(100) | no | Concepto (solo del negocio, nunca del hogar) | `alquiler del local`, `sueldo`, `venta fija a un comedor` |
| `monto` | decimal(12,2) | no | Monto por ocurrencia | `350.00` |
| `frecuencia` | frecuencia | no | Cada cuánto | `mensual` |
| `dia_semana` | smallint | sí | 1 = lunes … 7 = domingo (para `semanal`) | `6` |
| `dia_mes` | smallint | sí | 1–31 (para `quincenal` es el primer día; para `mensual`) | `28` |
| `es_sueldo` | boolean | no | Sueldo fijo del dueño (egreso, categoría retiro personal) | `true` |
| `fecha_inicio` | date | no | Desde cuándo rige | `2026-11-01` |
| `fecha_fin` | date | sí | Hasta cuándo (null = vigente) | |
| `activo` | boolean | no | | `true` |

> Un solo sueldo activo por empresa (índice único parcial). Cambiar el sueldo = cerrar el registro (`fecha_fin`) y crear otro, así queda el historial. La alerta `retiro_excesivo` compara los `retiro_personal` del periodo contra este monto.

#### `reglas_meta`
Metas plantilla y sus reglas automáticas (F8). **Grano:** una meta activada.

| Campo | Tipo | Nulo | Descripción | Ejemplo |
|---|---|---|---|---|
| `meta_id` | varchar(20) | PK | Identificador | `MET-0004` |
| `empresa_id` | varchar(20) | no | FK → `empresas` | |
| `plantilla` | plantilla_meta | no | Meta elegida | `apartar_para_pedido` |
| `programado_id` | varchar(20) | sí | FK → `movimientos_programados` (para `sueldo_fijo`) | |
| `tipo_regla` | tipo_regla | sí | Tipo de regla automática | `porcentaje_de_venta` |
| `valor` | decimal(12,4) | sí | 0.10 = 10 %, o monto fijo | `0.1000` |
| `destino` | varchar(30) | sí | Fondo virtual | `fondo_pedidos` |
| `objetivo` | decimal(12,2) | sí | Monto o días meta | `30` |
| `acumulado` | decimal(12,2) | no | Lo apartado (virtual: no sale de la caja) | `84.00` |
| `recordatorio_frecuencia` | frecuencia | sí | | `semanal` |
| `recordatorio_dia` | smallint | sí | | `1` |
| `estado` | estado_meta | no | | `activa` |
| `fecha_inicio` | date | no | | |
| `fecha_logro` | date | sí | | |

#### `forecast_ajustes`
Ajustes manuales del usuario sobre la proyección (contrato §4.2). **Grano:** un ajuste en una fecha.

| Campo | Tipo | Nulo | Descripción | Ejemplo |
|---|---|---|---|---|
| `ajuste_id` | varchar(20) | PK | Identificador | `AJU-0003` |
| `empresa_id` | varchar(20) | no | FK → `empresas` | |
| `programado_id` | varchar(20) | sí | FK → `movimientos_programados` si ajusta un recurrente | |
| `fecha` | date | no | Fecha afectada | `2026-11-28` |
| `concepto` | varchar(100) | no | | `alquiler` |
| `monto` | decimal(12,2) | no | Nuevo monto (0 = no se paga) | `0.00` |
| `motivo` | varchar(255) | sí | | `acuerdo con el dueño del local` |
| `activo` | boolean | no | | `true` |
| `creado_en` | timestamptz | no | | |

---

### 2.5 Alertas, conversación y consentimiento

#### `alertas`
Alertas y nudges (F6). **Grano:** una alerta generada.

| Campo | Tipo | Nulo | Descripción | Ejemplo |
|---|---|---|---|---|
| `alerta_id` | varchar(20) | PK | Identificador | `ALE-0101` |
| `empresa_id` | varchar(20) | no | FK → `empresas` | |
| `tipo` | tipo_alerta | no | Disparador | `faltante_caja` |
| `prioridad` | smallint | no | 1 a 8 según F6 | `1` |
| `fecha_evento` | date | no | Cuándo ocurriría el problema | `2026-11-30` |
| `monto` | decimal(12,2) | sí | Monto involucrado | `650.00` |
| `probabilidad` | decimal(4,3) | sí | Probabilidad estimada | `0.780` |
| `nivel_riesgo` | nivel_riesgo | sí | | `alto` |
| `causas` | json | sí | Causas con su impacto | `[{"causa":"retiro_mayor_al_usual","impacto":700}]` |
| `accion_sugerida` | varchar(50) | sí | Botón propuesto | `recordar_cliente` |
| `entidad_tipo` | varchar(30) | sí | Tabla del registro que la causa | `cuaderno_fiado` |
| `entidad_id` | varchar(20) | sí | ID de ese registro | `FIA-0045` |
| `canal` | canal_notificacion | no | | `whatsapp` |
| `estado` | estado_alerta | no | | `activa` |
| `accion_tomada` | varchar(50) | sí | Lo que hizo el usuario | `recordar_cliente` |
| `fecha_accion` | timestamptz | sí | | |
| `creada_en` | timestamptz | no | | |
| `enviada_en` | timestamptz | sí | Null si se retuvo por tope diario u horario silencioso | |
| `modelo_version` | varchar(30) | sí | Versión del forecast que la originó | |

> Métricas de F6: precision y recall de `faltante_caja` contra `saldo_diario.deficit_14d`; anticipación = `fecha_evento − creada_en`; % con acción = `accion_tomada` no nula.

#### `conversaciones`
Mensajes del chat con el asistente (F1.6 y F7). **Grano:** un mensaje.

| Campo | Tipo | Nulo | Descripción | Ejemplo |
|---|---|---|---|---|
| `mensaje_id` | varchar(20) | PK | Identificador | `MSG-0501` |
| `empresa_id` | varchar(20) | no | FK → `empresas` | |
| `conversacion_id` | varchar(20) | no | Agrupa mensajes de una sesión | `CNV-0040` |
| `rol` | rol_mensaje | no | | `asistente` |
| `canal` | canal_notificacion | no | | `whatsapp` |
| `texto` | text | sí | Contenido | `Hoy tienes S/ 2 340 en caja.` |
| `media_url` | varchar(255) | sí | Audio o foto adjunta | |
| `intencion` | varchar(50) | sí | Intención clasificada | `consulta_caja` |
| `herramientas_llamadas` | json | sí | Function calls y resultados | |
| `cifras_verificadas` | boolean | sí | Todas las cifras existen en los datos | `true` |
| `fallback_usado` | boolean | no | Se respondió con plantilla | `false` |
| `derivado_a_humano` | boolean | no | | `false` |
| `prompt_version` | varchar(30) | sí | | `asistente-v2` |
| `modelo_version` | varchar(30) | sí | | |
| `fecha_hora` | timestamptz | no | | |

#### `consentimientos`
Permiso para compartir el historial (roadmap, contrato §8.3). **Grano:** un consentimiento otorgado o revocado.

| Campo | Tipo | Nulo | Descripción | Ejemplo |
|---|---|---|---|---|
| `consentimiento_id` | varchar(20) | PK | Identificador | |
| `empresa_id` | varchar(20) | no | FK → `empresas` | |
| `alcance` | json | no | Qué se comparte | `["resumen_12_meses","score"]` |
| `activo` | boolean | no | Desactivado por defecto | `false` |
| `fecha_otorgado` | timestamptz | sí | | |
| `vigencia_hasta` | date | sí | | `2027-05-14` |
| `fecha_revocado` | timestamptz | sí | | |

---

### 2.6 Etiquetas y resultados

#### `saldo_diario`
Serie de saldo de cierre. **Grano:** una empresa en un día. PK `(empresa_id, fecha)`.

| Campo | Tipo | Nulo | Descripción | Ejemplo | Uso ML |
|---|---|---|---|---|---|
| `empresa_id` | varchar(20) | PK, FK | | | — |
| `fecha` | date | PK | | `2026-11-13` | feature |
| `saldo_cierre` | decimal(12,2) | no | Materializado desde `transacciones`; se regenera si llega un registro con fecha pasada | `2340.00` | feature (rezagos) |
| `deficit_14d` | boolean | sí | `true` si en los próximos 14 días el saldo cae bajo el mínimo operativo | `false` | **etiqueta** |

#### `eventos`
Shocks insertados por el generador sintético. **Grano:** un evento. **Toda la tabla es etiqueta.**

| Campo | Tipo | Nulo | Descripción | Ejemplo |
|---|---|---|---|---|
| `evento_id` | varchar(20) | PK | | |
| `empresa_id` | varchar(20) | no | FK → `empresas` | |
| `tipo_evento` | tipo_evento | no | | `retiro_excesivo` |
| `fecha_inicio` | date | no | | |
| `fecha_fin` | date | sí | | |
| `descripcion` | varchar(255) | sí | | `Retiro de S/ 700 extra para la casa` |

#### `predicciones_saldo`
Salidas del forecast de F3. **Grano:** empresa × fecha de corte × día proyectado × versión de modelo.

| Campo | Tipo | Nulo | Descripción | Ejemplo |
|---|---|---|---|---|
| `prediccion_id` | varchar(20) | PK | | |
| `empresa_id` | varchar(20) | no | FK → `empresas` | |
| `fecha_corte` | date | no | Último día con datos usados | `2026-11-14` |
| `fecha_objetivo` | date | no | Día proyectado | `2026-11-30` |
| `p10` / `p50` / `p90` | decimal(12,2) | no | Pesimista / esperado / optimista | `-410.00` / `-120.00` / `260.00` |
| `modelo_version` | varchar(30) | no | Baseline o modelo | `lgbm_cuantiles-0.3` |
| `creado_en` | timestamptz | no | | |

#### `predicciones_fiado`
Salidas del clasificador de riesgo de F4. **Grano:** fiado × fecha de corte × versión de modelo.

| Campo | Tipo | Nulo | Descripción | Ejemplo |
|---|---|---|---|---|
| `prediccion_id` | varchar(20) | PK | | |
| `fiado_id` | varchar(20) | no | FK → `cuaderno_fiado` | `FIA-0045` |
| `fecha_corte` | date | no | | `2026-11-14` |
| `prob_atraso` | decimal(4,3) | no | Probabilidad de pago tardío | `0.720` |
| `prob_pago_14d` | decimal(4,3) | sí | Pondera el cobro esperado en el forecast | `0.350` |
| `nivel_riesgo` | nivel_riesgo | no | | `alto` |
| `modelo_version` | varchar(30) | no | | `baseline_historial-1.0` |
| `creado_en` | timestamptz | no | | |

#### `score_salud`
Score mensual de F8. **Grano:** empresa × mes. PK `(empresa_id, mes)`.

| Campo | Tipo | Nulo | Descripción | Ejemplo |
|---|---|---|---|---|
| `empresa_id` | varchar(20) | PK, FK | | |
| `mes` | char(7) | PK | `AAAA-MM` | `2026-11` |
| `score` | smallint | no | 0 a 100 | `64` |
| `subindicadores` | json | no | Un valor por regla | `{"constancia_registro":80,"separacion_personal":55}` |
| `version_formula` | varchar(30) | no | | `score-v1` |

### 2.7 Técnicas (observabilidad; no son parte del modelo de negocio)

#### `llm_llamadas`
Una fila por llamada al LLM/VLM (OpenRouter), también las que fallan. **Grano:** una llamada. Se consulta con `GET /empresas/{id}/llm/llamadas` y `/llm/resumen`. Con `LLM_TRAZA_GUARDAR_CONTENIDO=false` no se guardan `messages` ni `content`.

| Campo | Tipo | Nulo | Descripción | Ejemplo |
|---|---|---|---|---|
| `llamada_id` | varchar(20) | PK | Identificador | `LLM-000001` |
| `empresa_id` | varchar(20) | sí | FK → `empresas` | `EMP-0001` |
| `origen` | varchar(20) | no | `extractor`, `asistente` o `vision` | `extractor` |
| `referencia_tipo` | varchar(20) | sí | `borrador` o `mensaje` | `borrador` |
| `referencia_id` | varchar(20) | sí | Registro que produjo la llamada (sin FK) | `BOR-7781` |
| `prompt_version` | varchar(30) | sí | | `extractor-v3` |
| `proveedor` | varchar(30) | no | | `openrouter` |
| `modelo_solicitado` | varchar(100) | sí | | `openai/gpt-4o-mini` |
| `modelo_respondido` | varchar(100) | sí | Modelo que realmente respondió | `openai/gpt-4o-mini-2024-07-18` |
| `generation_id` | varchar(100) | sí | `id` de la respuesta de OpenRouter | `gen-1731...` |
| `request` | json | sí | `messages`, `tools`, `tool_choice`, `temperature`, `max_tokens`. Las imágenes van como `{"imagen": {"sha256", "bytes", "mime"}}`; nunca el base64, headers ni la API key | |
| `respuesta` | json | sí | `content`, `tool_calls` crudos y `finish_reason` (o el `error` del proveedor) | |
| `prompt_tokens` | int | sí | ≥ 0 | `1480` |
| `completion_tokens` | int | sí | ≥ 0 | `60` |
| `total_tokens` | int | sí | ≥ 0 | `1540` |
| `costo_usd` | decimal(12,8) | sí | `usage.cost` de OpenRouter | `0.00026000` |
| `latencia_ms` | int | sí | Tiempo de la llamada HTTP | `1280` |
| `estado` | varchar(20) | no | `ok`, `timeout`, `http_error`, `red`, `respuesta_invalida`, `sin_configurar` | `ok` |
| `http_status` | smallint | sí | | `429` |
| `error` | text | sí | Mensaje corto, sin secretos | |
| `resultado_uso` | varchar(30) | sí | Qué hizo el consumidor con la salida: `aceptada`, `rechazada_validacion`, `rechazada_verificador` | `aceptada` |
| `creado_en` | timestamptz | no | | |

Índices: `(empresa_id, creado_en)` y `(origen, creado_en)`.

---

## 3. Vistas derivadas (no se guardan)

| Vista | Qué calcula | Fórmula |
|---|---|---|
| `v_saldo_caja` | Saldo actual de la caja del negocio | `saldo_inicial + Σ(+monto si ingreso, −monto si egreso)` sobre `transacciones` con `afecta_caja` y no `anulada` |
| `v_fiados` | `monto_pendiente`, `dias_atraso`, estado | `monto − Σ cobro_fiado`; atraso respecto a `fecha_compromiso` o al umbral X, **a la fecha de corte** |
| `v_deudas` | `monto_pendiente`, estado `pendiente / por_vencer / vencido / pagado` | `monto_total_a_pagar − Σ pagos`; `por_vencer` si vence en ≤ 3 días |
| `v_impuestos` | Semáforo `al_dia / vencido` | `fecha_pago IS NULL AND fecha_vencimiento < hoy` → `vencido` |
| `v_resumen_mes` | Indicadores de F2 | Ventas (incluye fiadas) − costo de lo vendido − gastos del negocio; retiros personales vs sueldo |
| `v_disponible_gastar` | "Disponible para gastar" de F3 | saldo + cobros esperados − pagos comprometidos hasta el próximo vencimiento grande − mínimo operativo − reserva de impuestos |

> El saldo de caja es **flujo de efectivo** (solo `afecta_caja`). La ganancia de F2 es **devengada**: cuenta las ventas fiadas aunque no se hayan cobrado.

---

## 4. Cómo se registra cada caso

| Lo que dice el usuario | `transacciones` | Otra tabla | ¿Mueve caja? |
|---|---|---|---|
| "vendí dos cervezas" | `venta`, `efectivo` + 1 `detalle_transaccion` | — | Sí, + |
| "le fié a la Sra. Carmen 2 panes y una leche" | `venta`, `credito`, `fiado_id` | nuevo `cuaderno_fiado` | No |
| "la Sra. Carmen me pagó 50" | `cobro_fiado`, `efectivo`, `fiado_id` | (si completa: `fecha_pago_total`) | Sí, + |
| "pedí 2 400 a Andina para pagar el 30" | `compra`, `credito`, `deuda_id` + detalle de productos | nueva `deudas` (`tipo = proveedor`) | No |
| "le pagué 1 200 a Andina" | `pago_proveedor`, `deuda_id` | — | Sí, − |
| "me prestaron 1 000, pago 40 diarios" | `prestamo_recibido`, `deuda_id` | nueva `deudas` (`prestamo_informal`, `frecuencia_cuota = diaria`) | Sí, + |
| "pagué la cuota del préstamo" | `pago_prestamo`, `deuda_id` | — | Sí, − |
| "saqué 50 para la casa" | `retiro_personal` (`programado_id` si es el sueldo) | — | Sí, − |
| "pagué el colegio de mi hijo" | Nada, salvo que la plata haya salido de la caja de la tienda → `retiro_personal` | — | Solo si salió de la caja |
| "pagué la luz, 80" | `gasto_negocio` (`programado_id` si es recurrente) | — | Sí, − |
| "pagué mi RUS, 20 soles" | `pago_impuesto`, `impuesto_id` | `impuestos.fecha_pago` | Sí, − |
| Yape/Plin recibido (API) | `venta`, `billetera_digital`, `billetera_mov_id` | `billeteras_digitales` | Sí, + |
| "mi sueldo va a ser 400 a la semana" | — | `movimientos_programados` (`es_sueldo = true`) | No (se proyecta) |
| "este mes no pago alquiler" | — | `forecast_ajustes` | No (se proyecta) |

Todo registro por voz, texto o foto pasa antes por `borradores`; el formulario web (`manual`) y la API de billeteras escriben directo.

---

## 5. Reglas para evitar fuga de datos

- En una `fecha_corte` solo se usan registros con `creado_en < fecha_corte` y pagos y atrasos ocurridos **antes** de esa fecha.
- `pago_tardio`, `deficit_14d` y toda la tabla `eventos` son **solo etiquetas**, nunca features.
- `clientes.perfil_pago` nunca entra al modelo; el riesgo se infiere del historial.
- `dias_atraso`, `monto_pendiente` y estados se calculan a la fecha de corte, nunca se leen de una columna guardada.
- Split temporal (entrenar con los primeros meses, evaluar con los últimos) y por empresa.

# Reporte de auditoría de calidad de datos

> Generado por [`data/audit_quality.mjs`](./audit_quality.mjs) el **2026-11-15T13:17:39.701Z** sobre `data/csv`, contra el esquema real de `backend/app/db/models.py` (exportado en `data/schema_esquema.json`).
> Estado: **APROBADO** (30 controles superados) sobre **63,736 filas** de las 25 tablas, **40 FK**, **46 CHECK** y **153 frases** de evaluación de ingesta.
> La capacidad de detección se demuestra con `node data/audit_mutations.mjs` (copias descartables con errores inyectados).

## 1. Controles

| # | Categoría | Regla | Estado | Evidencia |
|---:|---|---|:---:|---|
| 1 | A. Estructura | Los 25 CSV del modelo existen | **PASS** | 25/25 archivos |
| 2 | A. Estructura | Las columnas de cada CSV coinciden con las de la tabla (ninguna extra, ninguna obligatoria faltante) | **PASS** | columnas coinciden con schema_esquema.json |
| 3 | B. Columnas | NOT NULL: ninguna columna obligatoria vacía | **PASS** | 63736 filas revisadas |
| 4 | B. Columnas | Largo máximo de varchar(n)/char(n) (p. ej. IDs de 20 caracteres) | **PASS** | todos los textos caben en su columna |
| 5 | B. Columnas | Tipos: boolean, date, timestamptz, time, numeric(p,s), smallint/integer, JSON válidos | **PASS** | todos los valores tienen el formato de su columna |
| 6 | B. Columnas | Enums: cada valor pertenece a su tipo enumerado | **PASS** | todos los valores están en su enum |
| 7 | C. Llaves | PK únicas (simples y compuestas) en las 25 tablas | **PASS** | 63736 filas |
| 8 | C. Llaves | Todas las FK (40 relaciones del esquema) apuntan a un registro existente | **PASS** | 40 FK sin huérfanos |
| 9 | C. Llaves | UNIQUE e índices únicos (ruc, teléfono, nombre de rubro/categoría, un sueldo activo por empresa, impuesto y billetera 1-1…) | **PASS** | sin repetidos |
| 10 | D. CHECK | Los 46 CHECK de models.py se cumplen (afecta_caja, un solo vínculo, cobro/pago con su vínculo, moneda PEN, 0-1, RUC, periodos AAAA-MM…) | **PASS** | 46 CHECK evaluados sobre todas las filas |
| 11 | E. Negocio | Nada posterior a la hora de corte (10:00 del 2026-11-14, Lima): transacciones, fiados, pagos, predicciones, conversaciones, borradores | **PASS** | cero registros posteriores al corte; la venta "2 cervezas" y los movimientos de la demo no están cargados |
| 12 | E. Negocio | Cero fuga de datos: creado_en nunca es anterior a la fecha del hecho que registra salvo registro tardío explícito, y los pagos no preceden a su origen | **PASS** | orden temporal coherente |
| 13 | E. Negocio | saldo_diario = saldo inicial + Σ movimientos que afectan caja (todas las empresas, todos los días) | **PASS** | 4267 filas recalculadas |
| 14 | E. Negocio | Ninguna empresa tiene saldo de caja negativo | **PASS** | mínimo de cada empresa >= 0 |
| 15 | E. Negocio | deficit_14d recalculado (saldo < mínimo operativo en los 14 días siguientes); null si la ventana pasa del corte | **PASS** | etiqueta consistente |
| 16 | E. Negocio | Hay episodios reales de déficit en varias bodegas para medir recall (>= 5 empresas con deficit_14d = true) | **PASS** | 15 empresas con episodios |
| 17 | E. Negocio | detalle_transaccion: cantidades enteras, subtotal = cantidad x precio y Σ subtotales = monto de la transacción | **PASS** | 41998 líneas |
| 18 | E. Negocio | Categorías: cobros de fiado, préstamos, retiros, impuestos y cuotas en su categoría; ingresos en categorías de ingreso y egresos en categorías de egreso | **PASS** | categorías coherentes con el tipo |
| 19 | E. Negocio | Catálogo de categorías snake_case con cobro_fiados, prestamos_recibidos y otros_gastos; rubros bodega/restaurante/taller/distribuidora | **PASS** | 16 categorías y 4 rubros |
| 20 | E. Negocio | Borradores: payload legible con clave del backend, confirmados con su transacción y monto corregido coherente, confianza < 0.75 con pregunta aclaratoria | **PASS** | 3 borradores |
| 21 | E. Negocio | Alertas: causas {descripcion, monto}, entidad existente (plural) o `mes`, prioridad según el tipo, causas de pedido/retiro como las arma el backend | **PASS** | 18 alertas |
| 22 | E. Negocio | score_salud: 3 subindicadores con los pesos del backend (0.35 / 0.40 / 0.25) y score = suma ponderada | **PASS** | 170 scores |
| 23 | E. Negocio | Predicciones: nivel de riesgo con los umbrales del backend (>= 0.6 alto, >= 0.3 medio) y p10 <= p50 <= p90 | **PASS** | 31 de fiado y 60 de saldo |
| 24 | E. Negocio | Ninguna versión del forecast apunta a 'forecast-lgbm-quantile-0.3.1' (la del artefacto es lgbm_cuantiles-1.0) | **PASS** | versiones: lgbm_cuantiles-1.0, naive-estacional-0.1.0, reglas-alertas-0.2.0, riesgo-atraso-baseline-0.1.0 |
| 25 | E. Negocio | Empresas: tiene_ruc ⇔ ruc presente, dígito verificador SUNAT (módulo 11) válido y régimen/impuestos coherentes | **PASS** | 24/30 con RUC válido |
| 26 | E. Negocio | Heterogeneidad: volúmenes, rubros, trabajadores (1-5), billetera digital y empresas sin RUC distintos entre sí | **PASS** | 5 valores de n_trabajadores; 29 volúmenes distintos; 1292 movimientos de billetera |
| 27 | E. Negocio | Billeteras: cada pago por billetera_digital tiene su movimiento en billeteras_digitales (1-1) | **PASS** | 1292 movimientos enlazados |
| 28 | E. Negocio | Fiados, deudas e impuestos: fecha de pago total ⇔ pagos registrados que cubren el monto; nunca se cobra o paga de más | **PASS** | 152 fiados, 140 deudas, 136 impuestos |
| 29 | F. Evaluación de ingesta | Frases distintas y sin "(muestra N)", UTF-8 correcto, monto coherente con el catálogo de EMP-0001 y doble confirmación según la confianza | **PASS** | 153 frases distintas |
| 30 | G. Demo (informativo) | EMP-0001: saldo de caja al 2026-11-14 = S/ 2 340 (cifra de context.md §9) | **PASS** | saldo 2340 |

## 2. Filas por tabla

| Tabla | Filas |
|---|---:|
| `rubros` | 4 |
| `empresas` | 30 |
| `preferencias_alertas` | 30 |
| `categorias` | 16 |
| `productos` | 376 |
| `clientes` | 117 |
| `proveedores` | 82 |
| `borradores` | 3 |
| `transacciones` | 14,651 |
| `detalle_transaccion` | 41,998 |
| `cuaderno_fiado` | 152 |
| `deudas` | 140 |
| `billeteras_digitales` | 1,292 |
| `impuestos` | 136 |
| `movimientos_programados` | 81 |
| `reglas_meta` | 41 |
| `forecast_ajustes` | 4 |
| `alertas` | 18 |
| `conversaciones` | 4 |
| `consentimientos` | 10 |
| `saldo_diario` | 4,267 |
| `eventos` | 23 |
| `predicciones_saldo` | 60 |
| `predicciones_fiado` | 31 |
| `score_salud` | 170 |

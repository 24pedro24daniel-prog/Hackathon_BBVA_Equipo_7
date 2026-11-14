# Reporte de Auditoría Automática de Calidad del Dataset Sintético (MVP Bodegueros RUC 10 — 100 % Efectivo)

> Generado automáticamente por [`data/audit_quality.mjs`](./audit_quality.mjs) y [`data/pipeline_python/validate_pandera.py`](./pipeline_python/validate_pandera.py) con semilla fija `seed = 42`.
> **Estado global:** **100 % APROBADO (PASS)** (10/10 controles superados sobre **15,945 registros** en las 25 tablas del esquema y **150 casos** de evaluación de ingesta F1).

## 1. Matriz de Controles Ejecutados

| # | Categoría | Regla de negocio / contrato auditada | Estado | Evidencia cuantitativa |
|---:|---|---|:---:|---|
| 1 | Esquema Multi-Tabla (DBML) | 25 archivos CSV generados (24 tablas operativas pobladas + billeteras_digitales vacía con encabezados para roadmap) | **PASS** | Pobladas: 24/24 | billeteras_digitales: 0 filas |
| 2 | Público Objetivo (RUC 10) | 100% de empresas son bodegas (rubro_id='RUB-01') con RUC 10 de 11 dígitos (^10\d{9}$) activo (tiene_ruc=true) en 'nuevo_rus' | **PASS** | 30/30 bodegas RUC 10 (11 dígitos, ej. EMP-0001: 10456789012) en Nuevo RUS |
| 3 | Operación 100% Efectivo | 0 transacciones con métodos digitales (100% metodo_pago IN ('efectivo', 'credito') y 0 filas en billeteras_digitales) | **PASS** | Transacciones digitales: 0 | Efectivo/Crédito: 8102/8102 |
| 4 | Canales Manuales y Doble Confirmación (F1) | 100% canales manuales ('voz', 'texto', 'foto'), baja confianza (<0.75) con pregunta_aclaratoria y posibles duplicados etiquetados | **PASS** | Canales no manuales: 0 | Borradores <0.75: 3 | Eval <0.75: 30 | Eval duplicados: 10 |
| 5 | Criterio Bancario Sueldo ("Mínimo para vivir") | EMP-0001 registra sueldo fijo mensual bajo criterio bancario de mínimo para vivir (S/ 1,350.00) separado de retiros extra | **PASS** | Sueldo programado EMP-0001: S/ 1350.00 (sueldo fijo del dueño (criterio bancario mínimo para vivir S/ 1350/mes)) |
| 6 | Campaña Navideña y Nuevo RUS Mal Informado | Presencia de sobrecompra navideña en eventos.csv y casos donde ventas > S/ 5,000 pagan S/ 20 (Cat. 1) en vez de S/ 50 (Cat. 2) | **PASS** | RUS mal informado (S/ 20 con ventas > S/ 5,000): 11 empresas (incl. EMP-0001) | Cat. 2 S/ 50 correcto: 14 | Eventos campaña: 4 |
| 7 | Dominio y Restricciones CHECK (Pandera) | monto > 0, moneda == 'PEN', afecta_caja == (metodo_pago != 'credito') y <= 1 FK satélite en 100% de transacciones | **PASS** | 8102/8102 transacciones válidas (0 violaciones CHECK) |
| 8 | Integridad Referencial (PK/FK) | 100% de llaves foráneas en transacciones existen en sus tablas padre | **PASS** | Huérfanos detectados: 0 |
| 9 | Anti-Leakage (ML) | Cero transacciones o pagos de fiados con fecha posterior a fecha_corte (2026-11-14) | **PASS** | Transacciones futuras: 0 | Pagos futuros en cuaderno_fiado: 0 |
| 10 | Storytelling Pedro (EMP-0001) | Saldo en efectivo al 2026-11-14 (S/ 2,340.00), Ingresos Nov (S/ 8,540.00), Egresos Nov (S/ 7,310.00) y Fiados (S/ 310.00) cuadran al céntimo | **PASS** | Saldo: S/ 2340.00 | Ingresos: S/ 8540.00 | Egresos: S/ 7310.00 | Fiados: S/ 310.00 |

## 2. Resumen de Volúmenes por Tabla (`data/csv/*.csv`)

| Tabla | Registros | Observación de Calibración MVP |
|---|---:|---|
| `rubros.csv` | 4 | Validada sin huérfanos ni fuga de datos |
| `empresas.csv` | 30 | 30 bodegas RUC 10 (`rubro_id = RUB-01`, `tiene_ruc = true`, `nuevo_rus`) |
| `preferencias_alertas.csv` | 30 | Validada sin huérfanos ni fuga de datos |
| `categorias.csv` | 13 | Validada sin huérfanos ni fuga de datos |
| `productos.csv` | 133 | Validada sin huérfanos ni fuga de datos |
| `clientes.csv` | 89 | Validada sin huérfanos ni fuga de datos |
| `proveedores.csv` | 60 | Validada sin huérfanos ni fuga de datos |
| `conversaciones.csv` | 4 | Validada sin huérfanos ni fuga de datos |
| `borradores.csv` | 4 | Incluye casos con `confianza < 0.75` (`pregunta_aclaratoria`) y posibles duplicados |
| `movimientos_programados.csv` | 59 | Validada sin huérfanos ni fuga de datos |
| `cuaderno_fiado.csv` | 181 | Validada sin huérfanos ni fuga de datos |
| `deudas.csv` | 36 | Validada sin huérfanos ni fuga de datos |
| `billeteras_digitales.csv` | 0 | 0 registros (solo encabezados; operación MVP 100 % en efectivo, tabla reservada para roadmap) |
| `impuestos.csv` | 116 | Tramos Nuevo RUS SUNAT (S/ 20 y S/ 50) + casos de pago mal informado en campaña |
| `transacciones.csv` | 8,102 | 100 % `efectivo` o `credito` y canales manuales (`voz`, `texto`, `foto`) |
| `detalle_transaccion.csv` | 3,375 | Validada sin huérfanos ni fuga de datos |
| `reglas_meta.csv` | 29 | Validada sin huérfanos ni fuga de datos |
| `forecast_ajustes.csv` | 1 | Validada sin huérfanos ni fuga de datos |
| `alertas.csv` | 12 | Validada sin huérfanos ni fuga de datos |
| `consentimientos.csv` | 1 | Validada sin huérfanos ni fuga de datos |
| `saldo_diario.csv` | 3,455 | Validada sin huérfanos ni fuga de datos |
| `eventos.csv` | 13 | Validada sin huérfanos ni fuga de datos |
| `predicciones_saldo.csv` | 60 | Validada sin huérfanos ni fuga de datos |
| `predicciones_fiado.csv` | 22 | Validada sin huérfanos ni fuga de datos |
| `score_salud.csv` | 116 | Validada sin huérfanos ni fuga de datos |

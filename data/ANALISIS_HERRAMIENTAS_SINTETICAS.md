# Análisis Comparativo de Librerías de Generación de Datos Sintéticos para CajaClara

> Evaluación técnica de las 7 herramientas propuestas frente a la arquitectura de **25 tablas interconectadas** ([`modelo_datos.dbml`](../modelo_datos.dbml)), las restricciones `CHECK` ([`diccionario_datos.md`](../diccionario_datos.md)), las reglas anti-fuga de datos (`fecha_corte = 2026-11-14`) y el relato determinístico de **Bodega Don Pedro (`EMP-0001`)**.

---

## 1. Matriz de Evaluación Técnica frente al Modelo de Datos de CajaClara

| Librería / Repo | Categoría | Ventaja principal para CajaClara | Riesgo / Limitación en Hackathon (48 h) | Veredicto |
|---|---|---|---|---|
| **[`joke2k/faker`](https://github.com/joke2k/faker) + `NumPy/Pandas` (`seed=42`)** | Motor central determinístico y entidades sin PII | Control quirúrgico al céntimo sobre `EMP-0001` (`saldo = S/ 2,340.00`, `ingresos_nov = S/ 8,540.00`, `egresos_nov = S/ 7,310.00`, déficit `-S/ 650.00` el `30/11`) y 100 % de cumplimiento de los 8 `CHECK` de `transacciones`. | Requiere programar las reglas de negocio explícitamente (ya implementadas en [`generate_synthetic_data.mjs`](./generate_synthetic_data.mjs)). | **ELEGIDA (Núcleo Central)** |
| **[`sdv-dev/SDV`](https://github.com/sdv-dev/SDV)** (*Synthetic Data Vault*) | Síntesis estadística multi-tabla (`HMA`) | Excelente para documentar metadatos relacionales (`MultiTableMetadata`) y validar similitud estadística de distribuciones marginales. | **1)** HMA escala lento con >5 tablas y 25 tablas con FKs cruzadas (`borrador_id`, `fiado_id`, `deuda_id`, `impuesto_id`). **2)** Rompe restricciones condicionales complejas (`afecta_caja = (metodo_pago <> 'credito')` y `num_nonnulls <= 1`) si no se post-procesa. **3)** Necesita un dataset semilla previo para ajustar el sintetizador. | **USO PARCIAL (Solo esquema de metadatos, no como generador primario)** |
| **[`TimeSynth/TimeSynth`](https://github.com/TimeSynth/TimeSynth)** | Series temporales con estacionalidad y muestreo irregular | Su descomposición (`Señal armónica semanal + tendencia + ruido gaussiano + muestreo irregular`) modela muy bien los picos de fin de semana en bodega y los días que el usuario olvida anotar. | Librería antigua en Python (problemas de compatibilidad con `numpy >= 1.24`); su ecuación matemática se implementa directamente en 10 líneas de código determinístico sin dependencias frágiles. | **PATRÓN ADOPTADO (Ecuación armónica + ruido en el motor central)** |
| **[`ydataai/ydata-synthetic`](https://github.com/ydataai/ydata-synthetic)** | GANs para series temporales (`TimeGAN` / `DoppelGANger`) | Útil cuando se tienen miles de series reales bancarias y se quiere entrenar una red generativa. | Requiere GPU, entrenamiento largo, datos reales de entrada (inexistentes en el reto) y no garantiza que `saldo_inicial + Σ transacciones == saldo_diario`. | **DESCARTADA (Sobredimensionada para 48 h y sin GPU)** |
| **[`makcedward/nlpaug`](https://github.com/makcedward/nlpaug)** | Aumentación de texto/audio (errores fonéticos y OCR) | Ideal para inyectar ruido controlado en las 120–150 frases de F1: confusiones de OCR en cuaderno (`8` ↔ `3`/`0`, `5` ↔ `S`), errores fonéticos de Whisper (`vendí` → `bendi`, `cervezas` → `serbesas`) y jerga (`chelas`, `seño`). | Los diccionarios por defecto están en inglés; conviene combinarla con reglas fonéticas/OCR del español peruano ([`pipeline_python/augment_nlpaug_ingesta.py`](./pipeline_python/augment_nlpaug_ingesta.py)). | **ELEGIDA (Para el set de evaluación F1 de 120–150 casos)** |
| **[`Belval/TextRecognitionDataGenerator`](https://github.com/Belval/TextRecognitionDataGenerator)** | Generación de imágenes manuscritas para OCR | Permite renderizar líneas manuscritas sintéticas (`"Sra. Carmen - 2 panes, 1 leche - S/ 120"`) sobre fondo cuadriculado para probar F1.2 (`POST /ingesta/cuaderno`). | Según [`backend/PLAN_MVP.md`](../backend/PLAN_MVP.md) (Tarea A11), para la demo bastan 2–3 fotos de prueba del cuaderno. | **OPCIONAL (Solo para generar las 2–3 imágenes de prueba de F1.2)** |
| **[`pydantic`](https://github.com/pydantic/pydantic) + [`pandera-dev/pandera`](https://github.com/unionai-oss/pandera)** | Validación formal de contratos de datos y anti-leakage | Audita automáticamente DataFrames/CSVs completos (`monto > 0`, `moneda == 'PEN'`, `creado_en <= fecha_corte`, cero huérfanos en FKs) y genera evidencia técnica para el jurado (25 % IA/ML + 15 % Datos). | Ninguna: es rápida, declarativa y se integra directo con `pytest`. | **ELEGIDA (Auditoría de Calidad y Anti-Leakage)** |

---

## 2. Por qué la combinación ganadora es **Motor Determinístico (`Faker + Semilla Fija`) + `nlpaug` + `Pandera/Pydantic`**

En el modelo de CajaClara existen **tres requisitos duros** que ningún modelo generativo de caja negra (`SDV HMA`, `TimeGAN`) puede cumplir por sí solo sin romperse:

1. **Invariantes contables exactos entre tablas:**
   - `saldo_diario.saldo_cierre` **debe** ser exactamente igual a `empresas.saldo_inicial + Σ(ingresos que afectan caja) − Σ(egresos que afectan caja)` en `transacciones`.
   - En una venta fiada (`metodo_pago = 'credito'`), `transacciones.afecta_caja` debe ser `false` y su `fiado_id` debe existir en `cuaderno_fiado` con el mismo monto y fecha.
2. **El relato quirúrgico de Pedro (`EMP-0001`) al `2026-11-14`:**
   - El frontend, el backend y el pitch dependen de que en la base de datos de Render el saldo de `EMP-0001` sea exactamente **S/ 2,340.00**, los ingresos de noviembre **S/ 8,540.00** (`-6.2 %`), los egresos **S/ 7,310.00** (`+4.8 %`), los fiados pendientes **S/ 310.00** (`FIA-0045`, `FIA-0046`, `FIA-0047`), el pedido a *Distribuidora Andina* **S/ 2,400.00** (`PED-0012` al `2026-11-30`) y el déficit proyectado **-S/ 650.00**.
3. **Reglas estrictas contra Fuga de Datos (*Data Leakage*):**
   - Ninguna transacción ni pago de fiado usado en el corte `2026-11-14` puede tener `creado_en` o `fecha_pago_total` posterior a `2026-11-14`, y las etiquetas (`deficit_14d`, `pago_tardio`, `eventos`) deben ser coherentes con la serie futura real.

---

## 3. Arquitectura implementada en la carpeta `data/`

Sin modificar ningún archivo existente del repositorio compartido, dejamos listo en `data/` el flujo completo:

- [`data/schema.sql`](./schema.sql): DDL de los **19 ENUMs**, las **25 tablas** con todos sus `CHECK` e índices parciales, y las **6 vistas derivadas** (`v_saldo_caja`, `v_fiados`, `v_deudas`, `v_impuestos`, `v_resumen_mes`, `v_disponible_gastar`).
- [`data/generate_synthetic_data.mjs`](./generate_synthetic_data.mjs): Motor determinístico con semilla fija que genera las 25 tablas en `data/csv/*.csv` (**15,765 registros**) y las frases de evaluación en `data/eval/`.
- [`data/audit_quality.mjs`](./audit_quality.mjs) y [`data/pipeline_python/validate_pandera.py`](./pipeline_python/validate_pandera.py): Validadores automáticos de contratos y anti-leakage, con reporte generado en [`data/AUDITORIA_CALIDAD_DATOS.md`](./AUDITORIA_CALIDAD_DATOS.md) (**11/11 controles en PASS**).
- [`data/pipeline_python/augment_nlpaug_ingesta.py`](./pipeline_python/augment_nlpaug_ingesta.py): Aumentador de ruido fonético (voz) y manuscrito (OCR) para evaluar la ingesta F1.
- [`data/load_postgres.mjs`](./load_postgres.mjs) y [`data/load_postgres.py`](./load_postgres.py): Cargadores por lotes hacia PostgreSQL en Render leyendo `DATABASE_URL` desde `data/.env`.


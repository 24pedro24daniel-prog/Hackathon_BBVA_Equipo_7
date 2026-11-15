# Análisis Comparativo de Librerías de Generación de Datos Sintéticos para TuCaserito

> Evaluación técnica de las 7 herramientas propuestas frente a la arquitectura de **25 tablas del modelo (27 en la BD)** ([`modelo_datos.dbml`](../modelo_datos.dbml)), las restricciones `CHECK` ([`diccionario_datos.md`](../diccionario_datos.md)), las reglas anti-fuga de datos (`fecha_corte = 2026-11-14`) y el relato determinístico de **Bodega Don Pedro (`EMP-0001`)**.

---

## 1. Matriz de Evaluación Técnica frente al Modelo de Datos de TuCaserito

| Librería / Repo | Categoría | Ventaja principal para TuCaserito | Riesgo / Limitación en Hackathon (48 h) | Veredicto |
|---|---|---|---|---|
| **[`joke2k/faker`](https://github.com/joke2k/faker) + `NumPy/Pandas` (`seed=42`)** | Motor central determinístico y entidades sin PII | Control quirúrgico al céntimo sobre `EMP-0001` (`saldo = S/ 2,340.00`, `ingresos_nov = S/ 8,540.00`, `egresos_nov = S/ 7,310.00`, déficit `-S/ 650.00` el `30/11`) y cumplimiento de los 46 `CHECK` del esquema. En la práctica se implementó en **Node, sin Faker**: un PRNG propio (Mulberry32) por empresa. | Requiere programar las reglas de negocio explícitamente (ya implementadas en [`generate_synthetic_data.mjs`](./generate_synthetic_data.mjs)). | **ELEGIDA (Núcleo Central)** |
| **[`sdv-dev/SDV`](https://github.com/sdv-dev/SDV)** (*Synthetic Data Vault*) | Síntesis estadística multi-tabla (`HMA`) | Excelente para documentar metadatos relacionales (`MultiTableMetadata`) y validar similitud estadística de distribuciones marginales. | **1)** HMA escala lento con >5 tablas y 25 tablas con FKs cruzadas (`borrador_id`, `fiado_id`, `deuda_id`, `impuesto_id`). **2)** Rompe restricciones condicionales complejas (`afecta_caja = (metodo_pago <> 'credito')` y `num_nonnulls <= 1`) si no se post-procesa. **3)** Necesita un dataset semilla previo para ajustar el sintetizador. | **USO PARCIAL (Solo esquema de metadatos, no como generador primario)** |
| **[`TimeSynth/TimeSynth`](https://github.com/TimeSynth/TimeSynth)** | Series temporales con estacionalidad y muestreo irregular | Su descomposición (`Señal armónica semanal + tendencia + ruido gaussiano + muestreo irregular`) modela muy bien los picos de fin de semana en bodega y los días que el usuario olvida anotar. | Librería antigua en Python (problemas de compatibilidad con `numpy >= 1.24`); su ecuación matemática se implementa directamente en 10 líneas de código determinístico sin dependencias frágiles. | **PATRÓN ADOPTADO (Ecuación armónica + ruido en el motor central)** |
| **[`ydataai/ydata-synthetic`](https://github.com/ydataai/ydata-synthetic)** | GANs para series temporales (`TimeGAN` / `DoppelGANger`) | Útil cuando se tienen miles de series reales bancarias y se quiere entrenar una red generativa. | Requiere GPU, entrenamiento largo, datos reales de entrada (inexistentes en el reto) y no garantiza que `saldo_inicial + Σ transacciones == saldo_diario`. | **DESCARTADA (Sobredimensionada para 48 h y sin GPU)** |
| **[`makcedward/nlpaug`](https://github.com/makcedward/nlpaug)** | Aumentación de texto/audio (errores fonéticos y OCR) | Habría servido para inyectar ruido en las frases de F1 (`8` ↔ `3`, `vendí` → `bendi`, `chelas`). | Los diccionarios por defecto están en inglés y el equipo nunca la integró (el script anterior la nombraba pero no la usaba). | **DESCARTADA: se usan reglas fonéticas/OCR propias del español peruano en [`pipeline_python/aumentar_ruido_ingesta.py`](./pipeline_python/aumentar_ruido_ingesta.py) (sin `nlpaug`)** |
| **[`Belval/TextRecognitionDataGenerator`](https://github.com/Belval/TextRecognitionDataGenerator)** | Generación de imágenes manuscritas para OCR | Permite renderizar líneas manuscritas sintéticas (`"Sra. Carmen - 2 panes, 1 leche - S/ 120"`) sobre fondo cuadriculado para probar F1.2 (`POST /ingesta/cuaderno`). | Según [`backend/PLAN_MVP.md`](../backend/PLAN_MVP.md) (Tarea A11), para la demo bastan 2–3 fotos de prueba del cuaderno. | **OPCIONAL (Solo para generar las 2–3 imágenes de prueba de F1.2)** |
| **[`pydantic`](https://github.com/pydantic/pydantic) + [`pandera-dev/pandera`](https://github.com/unionai-oss/pandera)** | Validación formal de contratos de datos y anti-leakage | Audita automáticamente DataFrames/CSVs completos (`monto > 0`, `moneda == 'PEN'`, `creado_en <= fecha_corte`, cero huérfanos en FKs) y genera evidencia técnica para el jurado (25 % IA/ML + 15 % Datos). | Ninguna: es rápida, declarativa y se integra directo con `pytest`. | **ELEGIDA como chequeo complementario ([`validate_pandera.py`](./pipeline_python/validate_pandera.py)); el auditor principal es [`audit_quality.mjs`](./audit_quality.mjs)** |

---

## 2. Por qué la combinación ganadora es **motor determinístico (semilla fija) + auditor contra el esquema real + Pandera**

En el modelo de TuCaserito existen **tres requisitos duros** que ningún modelo generativo de caja negra (`SDV HMA`, `TimeGAN`) puede cumplir por sí solo sin romperse:

1. **Invariantes contables exactos entre tablas:**
   - `saldo_diario.saldo_cierre` **debe** ser exactamente igual a `empresas.saldo_inicial + Σ(ingresos que afectan caja) − Σ(egresos que afectan caja)` en `transacciones`.
   - En una venta fiada (`metodo_pago = 'credito'`), `transacciones.afecta_caja` debe ser `false` y su `fiado_id` debe existir en `cuaderno_fiado` con el mismo monto y fecha.
2. **El relato quirúrgico de Pedro (`EMP-0001`) al `2026-11-14`:**
   - El frontend, el backend y el pitch dependen de que en la base de datos de Render el saldo de `EMP-0001` sea exactamente **S/ 2,340.00**, los ingresos de noviembre **S/ 7,976.00** (`-3.0 %`), los egresos **S/ 6,697.70** (`+3.0 %`), los fiados pendientes **S/ 310.00** (`FIA-0045`, `FIA-0046`, `FIA-0047`), el pedido a *Distribuidora Andina* **S/ 2,400.00** (`PED-0012` al `2026-11-30`) y el déficit proyectado **-S/ 650.00** el 30/11 con el forecast LightGBM del backend (calibrado en el generador, §2.2).
3. **Reglas estrictas contra Fuga de Datos (*Data Leakage*):**
   - Ninguna transacción ni pago de fiado usado en el corte `2026-11-14` puede tener `creado_en` o `fecha_pago_total` posterior a `2026-11-14`, y las etiquetas (`deficit_14d`, `pago_tardio`, `eventos`) deben ser coherentes con la serie futura real.

---

## 3. Arquitectura implementada en la carpeta `data/`

- [`pipeline_python/generar_schema.py`](./pipeline_python/generar_schema.py): genera [`schema.sql`](./schema.sql) (19 ENUM, 27 tablas, CHECK, únicos e índices; **sin vistas**) y [`schema_esquema.json`](./schema_esquema.json) **desde `backend/app/db/models.py`**, la fuente de verdad. `--check` verifica que estén al día.
- [`generate_synthetic_data.mjs`](./generate_synthetic_data.mjs): motor determinístico (`seed = 42`) que escribe los 25 CSV de `data/csv/` (**63 736 registros**) y, con [`eval_ingesta.mjs`](./eval_ingesta.mjs), las 153 frases de `data/eval/`.
- [`audit_quality.mjs`](./audit_quality.mjs): valida los CSV contra el esquema real (PK, 40 FK, NOT NULL, tipos y largos, enums, 46 CHECK y reglas de negocio; **30 controles**) y escribe [`AUDITORIA_CALIDAD_DATOS.md`](./AUDITORIA_CALIDAD_DATOS.md) con la fecha real. [`audit_mutations.mjs`](./audit_mutations.mjs) comprueba que detecta 22 errores inyectados. [`validate_pandera.py`](./pipeline_python/validate_pandera.py) es un chequeo complementario independiente.
- [`pipeline_python/aumentar_ruido_ingesta.py`](./pipeline_python/aumentar_ruido_ingesta.py): variantes con ruido fonético/OCR de las frases de evaluación (reglas propias).
- [`load_postgres.py`](./load_postgres.py) y [`load_postgres.mjs`](./load_postgres.mjs): crean el esquema desde `schema.sql`, cargan los CSV por `COPY`/lotes en orden de FK y validan conteos. Rechazan producción salvo con `--produccion --confirmar <bd>`. El backend tiene además `python -m app.db.cargar_csv`.

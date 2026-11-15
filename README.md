# TuCaserito

TuCaserito es un copiloto de orden y maduración financiera diseñado específicamente para **bodegueros de barrio con RUC 10 en Perú que operan 100% en efectivo (*cash*)** y llevan sus cuentas de forma manual en cuadernos físicos. Ayuda a digitalizar ventas, fiados y pagos a proveedores; separar el capital del negocio del **mínimo para vivir**; corregir errores al informar impuestos; y anticipar faltantes de caja antes de los vencimientos.

El producto combina una interfaz conversacional autenticada (inspirada en mensajería para registrar movimientos en segundos sin usar bots abiertos en WhatsApp por seguridad bancaria) con un dashboard operativo que muestra el arqueo de efectivo, obligaciones y proyecciones a 30 días. El caso de uso de la demo es Pedro, bodeguero ficticio RUC 10. Todos los nombres, movimientos y montos de demostración son sintéticos.

*(Nota de identidad visual: TuCaserito es una solución independiente con marca e interfaz propias; no utiliza logos, colores ni interfaces bancarias oficiales como si fuera un producto del banco.)*

## El problema

Los bodegueros RUC 10 tradicionales cobran exclusivamente en efectivo y llevan sus cuentas en cuadernos de papel o de memoria, formando parte del núcleo de "No Clientes" invisibles para la banca comercial. Guardan todo el dinero en un solo cajón ("caja única"), mezclan los gastos del negocio con su subsistencia diaria y no tienen claro cuánto les deben ni cuándo vencen sus proveedores.

En campañas estacionales fuertes —como la **campaña navideña**— suelen pedir mercadería de más sin prever sus vencimientos de caja. Además, aunque muchos **sí cumplen con pagar su impuesto básico (Nuevo RUS), lo informan o calculan mal** (confundiendo los tramos de cuota S/ 20 vs. S/ 50 cuando suben sus ventas o registrándolo mezclado con gastos personales). Cuando aparece un faltante, recurren a préstamos informales costosos ("gota a gota"). TuCaserito ordena su información y previene crisis de liquidez sin alterar su rutina en mostrador.

Las referencias y el sustento del problema están documentados en [context.md](./context.md). Las cifras externas deben presentarse junto con sus fuentes; las conversaciones del equipo son evidencia cualitativa y no deben exponerse como estadísticas generales.

## Objetivos del MVP

- Registrar movimientos en efectivo mediante **foto del cuaderno, voz y texto manual**, con **doble confirmación** ante ambigüedades y posibilidad de corregir.
- Realizar el arqueo de efectivo separando el flujo en **3 cubetas**: gastos operativos/mercadería, **mínimo para vivir** (gastos fijos personales) y gastos personales extra, calculando un **sueldo mensual fijo bajo criterio bancario**.
- Proyectar el saldo diario de efectivo a 30 días (incorporando campañas como Navidad y días sin registro), señalar riesgos de faltante y simular escenarios ("What-If").
- Dar seguimiento a fiados, deudas con proveedores y auditar el registro correcto del Nuevo RUS.
- Explicar alertas y cifras con datos verificables, supuestos, límites y nivel de confianza.
- Medir hábitos financieros con un índice pedagógico de maduración explicable.

## Funcionalidades

1. **Registro multicanal con doble confirmación:** captura mediante **foto del cuaderno físico (OCR/Visión), voz y texto manual** dentro de la app autenticada. Ante letra manuscrita poco legible, mala pronunciación o abreviaturas ambiguas, exige doble confirmación antes de guardar. Los posibles duplicados (ej. un apunte dictado por voz y luego fotografiado en el cuaderno) se señalan para revisión humana: nunca se borran ni combinan automáticamente.
2. **Resumen financiero y sueldo bancario:** arqueo de efectivo disponible, ingresos y egresos del mes desglosados en las 3 cubetas, ganancia aproximada, retiros personales vs. **sueldo fijo sugerido** (promedio histórico de gastos fijos para vivir), fiados por cobrar y pagos pendientes.
3. **Proyección de caja (30 días):** horizonte diario con rango pesimista/esperado/optimista, estacionalidad semanal y de campañas (Navidad), saldo mínimo operativo, alertas de déficit y monto **"disponible para gastar hoy"**.
4. **Fiados, proveedores y auditoría de impuestos:** seguimiento de cobros vencidos, calendario de pagos a proveedores, chequeo preventivo antes de pedir stock de campaña, y verificación del tramo/clasificación del **Nuevo RUS** ("paga, pero informa mal").
5. **Análisis:** evolución de ingresos y egresos en efectivo por categoría, producto, proveedor o periodo, con comparativa anónima frente a bodegas RUC 10 similares.
6. **Alertas:** avisos preventivos priorizados ("justo a tiempo"), con evidencia exacta ("¿Por qué veo esto?") y una acción sugerida de un toque; máximo dos al día y respetando horario silencioso.
7. **Asistente:** responde consultas y simula cambios en la caja usando motores determinísticos en Python vía *function calling*; no inventa ni calcula cifras por su cuenta.
8. **Progreso:** ruta de metas y un índice pedagógico de maduración financiera basado en hábitos observables.

## Uso responsable y límites

- El índice de maduración es educativo y explicable. No es un score crediticio, no estima elegibilidad y no determina decisiones de préstamo.
- El asistente puede explicar conceptos generales (como el funcionamiento básico del Nuevo RUS o el costo del crédito informal) y simular el efecto de acciones sobre la caja del negocio. No recomienda ni selecciona préstamos, productos financieros, prestamistas o entidades específicas, ni da asesoría tributaria o legal formal.
- Un historial estructurado podría compartirse o exportarse en el futuro para una revisión humana con un asesor bancario, solo con consentimiento explícito, desactivado por defecto y revocable. Esto no automatiza una decisión ni garantiza aprobación, acceso o mejores condiciones.
- La aplicación no ejecuta operaciones financieras reales, no otorga créditos y no promete aprobaciones ni rentabilidad.
- Los datos de demo son sintéticos (`seed=42`). Las estimaciones y salidas de modelos deben mostrar su origen, supuestos, límites, confianza y trazabilidad. El usuario conserva siempre la decisión final.
- No se deben incluir credenciales, datos bancarios reales ni información personal real.

## Alcance de la demo y potencial de expansión

- **Flujo principal:** registrar una venta/apunte en efectivo mediante foto de cuaderno y voz (activando doble confirmación y detección de duplicados), revisar el arqueo de efectivo frente al sueldo fijo ("mínimo para vivir"), detectar un error de tramo en el Nuevo RUS, entender un faltante proyectado para el **30/11 por sobrecompra de campaña navideña**, ver sus causas y simular alternativas. El relato sintético usa un saldo de S/ 2 340, un pago de S/ 2 400 a Distribuidora Andina, un déficit de S/ 650 y S/ 310 en fiados pendientes.
- **Prioridad del MVP:** registro por voz/texto/foto con doble confirmación, pedidos a crédito de proveedores, auditoría básica de Nuevo RUS, consulta del estado, resumen financiero con 3 cubetas, forecast a 30 días, cuentas por cobrar/pagar y alertas principales. Para la demo se acotan algunas intenciones del asistente, tres subindicadores principales del índice y dos gráficos analíticos.
- **Potencial de expansión (Roadmap):** una vez validado en bodegas RUC 10 en efectivo, la arquitectura parametrizada (`rules.json`) escala hacia bodegas con billeteras digitales (Yape/Plin) y POS, otros rubros minoristas RUC 10 (ferreterías, farmacias de barrio, bazares, restaurantes), comparación con pares reales y exportación consentida de historial para evaluación humana.

## Arquitectura y enfoque técnico

- **Frontend ([`frontend/`](./frontend/)):** Aplicación web *mobile-first* (`360px`) en **React 19 + Vite + React Router**, con las 6 vistas operativas del MVP (`Inicio`, `Proyección 30 días`, `Simulador`, `Cuentas`, `Progreso` y `Chat`). Soporta modo interactivo autónomo con mocks (`VITE_USE_MOCK=true`, incluyendo selector de escenario de Pedro con 3 meses de historial vs. Día 3 y modo degradado sin IA) o conexión en vivo al backend (`/api/v1`).
- **Backend y Motores Determinísticos ([`backend/`](./backend/)):** API REST en **FastAPI + SQLAlchemy 2 + PostgreSQL 16** bajo `/api/v1` según [`contract.md`](./contract.md). Incluye motores determinísticos para arqueo de caja, proyección estacional con bandas `P10/P50/P90`, chequeo preventivo de pedidos, simulador *What-If*, evaluación de las 4 reglas de alertas y cálculo del índice de salud financiera.
- **Voz, Visión (Cuaderno) y Asistente IA:**
  - Transcripción de notas de voz con **`faster-whisper`**.
  - Lectura de fotos del cuaderno de fiados mediante modelo de visión (**VLM** vía OpenRouter, con emparejamiento de clientes por alias, descarte de tachaduras y *fallback* determinístico por *fixtures* cuando no hay conexión o clave).
  - Extracción estructurada y asistente conversacional con *tool calling* sobre **OpenRouter** y *fallback* por reglas determinísticas (`app/services/ingesta/reglas.py`), más trazabilidad completa en la tabla `llm_llamadas` y subida opcional de medios con URLs prefirmadas en **Cloudflare R2**.
- **Pipeline de Datos Sintéticos y Auditoría ([`data/`](./data/)):** Generador determinístico (`seed=42`, [`generate_synthetic_data.mjs`](./data/generate_synthetic_data.mjs)) que produce **22 tablas CSV** (`37 164` registros) para **30 bodegas RUC 10 (`10xxxxxxxxx`) en Nuevo RUS**, operando 100% en efectivo/crédito con ingesta manual (`voz`, `texto`, `foto`). Incluye auditoría automatizada de 10 criterios ([`audit_quality.mjs`](./data/audit_quality.mjs) y [`AUDITORIA_CALIDAD_DATOS.md`](./data/AUDITORIA_CALIDAD_DATOS.md)), validación estadística de esquemas con **Pandera** ([`validate_pandera.py`](./data/pipeline_python/validate_pandera.py)) y corpus de evaluación de ingesta con ruido OCR/ASR de **NLPAug** (`180` frases en [`eval/frases_ingesta_eval.csv`](./data/eval/frases_ingesta_eval.csv)).
- **Modelos de Machine Learning ([`modelo/`](./modelo/)):**
  - **Forecast diario (`LightGBM Quantile Regression`):** Notebook [`modelo_ingreso_egreso_lightgbm.ipynb`](./modelo/modelo_ingreso_egreso_lightgbm.ipynb) y artefactos `.joblib` en [`modelo/artifacts/forecast/`](./modelo/artifacts/forecast/) para predecir cuantiles `P10`, `P50` y `P90` de ingresos y egresos diarios (`MAE` de `S/ 31.75` en ingreso y `S/ 11.43` en egreso, superando al baseline naive en **+34.5%** y **+68.1%** con cobertura `P10–P90` de ~78%).
  - **Score pedagógico / riesgo (`Logistic Regression`):** Notebook [`credit_scoring_bodegas_logreg.ipynb`](./modelo/credit_scoring_bodegas_logreg.ipynb) y artefactos serializados en [`modelo/artifacts/credit_scoring/`](./modelo/artifacts/credit_scoring/) (`AUC test = 0.771`).

## Estructura del repositorio

| Ruta | Contenido |
| :--- | :--- |
| [`frontend/`](./frontend/) | App web React 19 + Vite (6 pantallas del MVP, modo mock y cliente API con `X-API-Key` e `Idempotency-Key`). |
| [`backend/`](./backend/) | API FastAPI, modelos SQLAlchemy (25 tablas), `seed_demo.py`, motores financieros, ingesta IA, Docker Compose y suite de `pytest` (`test_a_*`, `test_b_*`, `eval_forecast`, `eval_extractor`). |
| [`data/`](./data/) | Generador sintético (`generate_synthetic_data.mjs`), 22 CSVs (`data/csv/`), DDL PostgreSQL (`schema.sql`), auditoría de calidad (`10/10 PASS`), validación Pandera y aumentación NLPAug. |
| [`modelo/`](./modelo/) | Notebooks de entrenamiento (`LightGBM` por cuantiles y `LogisticRegression`) y artefactos `.joblib` exportados en [`modelo/artifacts/`](./modelo/artifacts/). |
| [`PRODUCT.md`](./PRODUCT.md) | Definición de usuarios, propósito, posicionamiento y principios de diseño del producto. |
| [`context.md`](./context.md) | Problemática, sustento con fuentes, objetivos, funcionalidades y guion de demo de Pedro (`EMP-0001`). |
| [`contract.md`](./contract.md) | Especificación completa de contratos de la API REST (`/api/v1`). |
| [`diccionario_datos.md`](./diccionario_datos.md) / [`modelo_datos.dbml`](./modelo_datos.dbml) | Diccionario de las 25 entidades del modelo relacional y esquema DBML. |
| [`docs/arquitectura.drawio`](./docs/arquitectura.drawio) | Diagrama de arquitectura del sistema. |

## Instrucciones de ejecución (Local)

### 1. Frontend (React + Vite)
Por defecto corre con los mocks interactivos de la historia de Pedro sin requerir base de datos:
```bash
cd frontend
npm install
npm run dev
# Disponible en http://localhost:5173
```
*(Para conectarlo al backend real, configura `VITE_USE_MOCK=false`, `VITE_PROXY_TARGET=http://localhost:8000` y `VITE_API_KEY` en `frontend/.env`).*

### 2. Backend + Base de Datos (Docker Compose — recomendado)
```bash
cd backend
cp example.env .env   # Configura POSTGRES_USER, POSTGRES_PASSWORD y API_KEY
docker compose up -d
docker compose run --rm backend python -m app.db.reset
# API en http://localhost:8000 | Swagger UI en http://localhost:8000/docs
```
Para ejecutar las pruebas automatizadas y los *backtests*:
```bash
docker compose run --rm backend pytest -q
docker compose run --rm backend python -m tests.eval_forecast
docker compose run --rm backend python -m tests.eval_extractor
```

### 3. Generación y validación del Dataset Sintético (`data/`)
```bash
node data/generate_synthetic_data.mjs
node data/audit_quality.mjs
python data/pipeline_python/validate_pandera.py
python data/pipeline_python/augment_nlpaug_ingesta.py
```

### 4. Entrenamiento y exportación de Modelos ML (`modelo/`)
```bash
python -m nbconvert --to notebook --execute --inplace modelo/modelo_ingreso_egreso_lightgbm.ipynb
python -m nbconvert --to notebook --execute --inplace modelo/credit_scoring_bodegas_logreg.ipynb
```

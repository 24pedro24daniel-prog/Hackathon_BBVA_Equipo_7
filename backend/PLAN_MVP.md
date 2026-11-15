# TuCaserito — Plan del backend (MVP) para 2 desarrolladores

> Alcance: solo el MVP (Estadio 2, [context.md](../context.md) §7). Stack: **FastAPI + SQLAlchemy 2 + PostgreSQL local**.
> Contrato de referencia: [contract.md](../contract.md). Tablas: [modelo_datos.dbml](../modelo_datos.dbml) · [diccionario_datos.md](../diccionario_datos.md).

---

## 1. La idea de la división

El backend se parte por **lado del dato**, no por pantalla:

| | **Dev A — Ingesta y conversación** | **Dev B — Motores financieros** |
|---|---|---|
| Qué hace | Todo lo que **escribe** en la BD y todo lo que habla con IA de lenguaje (Whisper, LLM) | Todo lo que **lee y calcula** sobre la BD: saldos, proyección, cuentas, alertas |
| Funcionalidades | F1 (1.1, 1.2, 1.4, 1.5), movimientos, F7, F8 | F2, F3, F4, simulador, F5, F6, `/health` |
| Naturaleza | Integración con modelos de lenguaje + reglas de registro | Cálculo determinístico + integración con el modelo de ML |

Por qué así no se chocan:
- **Carpetas con dueño.** Cada uno edita solo sus archivos (§3). Los archivos compartidos se cierran al terminar la Fase 0.
- **Un único punto de contacto en código:** un puñado de funciones con firma congelada (§4). Mientras el otro no termina, esas funciones devuelven los JSON del mock del contrato, así nadie espera a nadie.
- A escribe las tablas, B las lee. Ninguno modifica las tablas del otro "por su cuenta".

---

## 2. Decisiones técnicas comunes

| Tema | Decisión |
|---|---|
| BD | PostgreSQL 16 en Docker (`backend/docker-compose.yml`, servicio `db`, `postgres:16.14`, publicado en el host como `localhost:5433` porque el 5432 puede estar ocupado por un PostgreSQL nativo). Crea también la BD de pruebas `cajaclara_test`. Respeta `decimal`, `timestamptz`, `json` e índices parciales del DBML. Cada dev usa **su propia BD local**. |
| ORM | SQLAlchemy 2.0 (estilo `Mapped[]`) + `psycopg` 3. Dinero siempre `Numeric(12,2)` → `Decimal`, nunca `float`. |
| Migraciones | Sin Alembic en el hackathon: `python -m app.db.reset` borra, crea (`create_all`) y siembra. Evita conflictos de migraciones entre los dos. |
| Vistas derivadas | Funciones Python con `fecha_corte` (no vistas SQL), en `services/finanzas/consultas.py`. Más fácil de testear y de reutilizar en el forecast. |
| Config | `pydantic-settings` (`core/config.py`) lee 3 archivos de `backend/`: **`parametros.env`** (no secretos, versionado: host/puerto/BD, `FECHA_DEMO`, `TZ=America/Lima`, `LLM_*`, `WHISPER_*`, `UMBRAL_CONFIANZA`), **`.env`** (solo credenciales, NO versionado: `POSTGRES_USER`, `POSTGRES_PASSWORD`, `API_KEY`, `OPENROUTER_API_KEY`, `R2_*`, `DATABASE_URL_PRODUCCION`, `AUTH_SECRET`, `AUTH_CREDENCIALES`) y **`example.env`** (plantilla versionada de `.env`). Las variables de entorno reales tienen prioridad. `DATABASE_URL` se compone de las partes (override opcional con `DATABASE_URL`). |
| Media (audio/foto) | Subida directa del front a **Cloudflare R2** con URL PUT prefirmada (`POST /media/subidas`); `media_url = "r2://<clave>"`, clave `empresas/{empresa_id}/{audios o fotos}/AAAA/MM/uuid.ext`. Lectura con `boto3` solo de claves de la empresa (anti-SSRF), tipo/tamaño verificados con HEAD y temporal borrado. Config: `R2_ACCOUNT_ID`, `R2_BUCKET`, `R2_PRESIGN_TTL_S`, `MEDIA_MAX_*_BYTES`, `MEDIA_TIPOS_*` en `parametros.env`; `R2_ACCESS_KEY_ID` y `R2_SECRET_ACCESS_KEY` en `.env`. `file://`/`demo://` se mantienen para demo y tests. |
| LLM y voz | LLM por **OpenRouter** (API compatible con OpenAI, `/chat/completions` con `tools`), cliente `httpx` en `services/ingesta/llm_client.py`. Whisper con **faster-whisper local** (`small`, CPU, `int8`), carga perezosa. |
| Docker | `backend/Dockerfile` (`python:3.12.15-slim`, usuario no root) + `docker-compose.yml` (`db` + `backend`, `env_file: [parametros.env, .env]`, volumen de caché de Whisper). |
| Puerto | `uvicorn app.main:app --port 8000 --no-proxy-headers` (el front ya proxea `/api` a `localhost:8000`). Prefijo `/api/v1`. |
| Autenticación | `POST /auth/login` (3 usuarios de demo, hash scrypt en `AUTH_CREDENCIALES`) → token HS256 de 8 h con `AUTH_SECRET`; las rutas protegidas aceptan `Authorization: Bearer` (solo su empresa: `core/alcance.py` revisa path, query y body → `403 EMPRESA_NO_PERMITIDA`) o `X-API-Key` (bot/admin). Límites en memoria: logins fallidos por IP y usos de IA por sesión/usuario (`429` + `Retry-After`). CORS `localhost:5173`, `cclara.site`, `www.cclara.site`, sin cookies. Ver `contract.md` §12. |
| Fecha "hoy" | Variable `FECHA_DEMO=2026-11-14` en `.env`: todos los cálculos usan `core/reloj.py::hoy()`, no `date.today()`. Así la demo de Pedro es reproducible. |
| Ramas | `back/base` (Fase 0) → luego `back/ingesta` (A) y `back/motores` (B). Merge a `main` en cada checkpoint (§6). |
| Tests | `pytest` + BD de prueba. Archivos `tests/test_a_*.py` (A) y `tests/test_b_*.py` (B). |

Dependencias (`requirements.txt`, todas con versión exacta `==`): `fastapi`, `uvicorn[standard]`, `python-multipart`, `sqlalchemy` 2.x, `psycopg[binary]` 3.x, `pydantic` 2.x, `pydantic-settings`, `tzdata`, `httpx` (OpenRouter), `faster-whisper`, `boto3` (R2), `pytest`, y para los modelos de ML del equipo de datos `lightgbm`, `scikit-learn`, `pandas`, `numpy`, `scipy`, `joblib` (+ `libgomp1` en la imagen).

---

## 3. Estructura de carpetas y dueños

```text
backend/
├── parametros.env                    F0 (B) — parámetros no secretos (versionado)
├── example.env                       F0 (B) — plantilla de credenciales (versionado)
├── .env                              local — solo credenciales, NO se versiona
├── Dockerfile, docker-compose.yml    F0 — db (postgres:16.14) + backend; docker/initdb crea cajaclara_test
├── requirements.txt                  F0 (B)
├── app/
│   ├── main.py                       F0 (B) — registra TODOS los routers desde el inicio
│   ├── core/                         F0 (B) — compartido, se congela tras F0
│   │   ├── config.py                 settings desde .env
│   │   ├── auth.py                   Bearer (sesión de una empresa) o X-API-Key; límite de uso de IA
│   │   ├── alcance.py                alcance por empresa del Bearer (path, query y body)
│   │   ├── tokens.py, claves_demo.py token HS256 y hash scrypt de las contraseñas de demo (CLI para regenerarlo)
│   │   ├── limites.py                ventanas deslizantes en memoria e IP real del cliente
│   │   ├── errors.py                 handler → formato { "error": {codigo, mensaje, detalles, request_id} }
│   │   ├── ids.py                    nuevo_id(db, Modelo, "MOV", ancho=6) → "MOV-000123"
│   │   ├── meta.py                   construye el bloque `meta` (request_id, latencia, versión, fallback)
│   │   ├── paginacion.py             limit/cursor → next_cursor
│   │   └── reloj.py                  hoy() / ahora() con FECHA_DEMO y zona America/Lima
│   ├── db/                           F0 (A) — compartido, se congela tras F0
│   │   ├── base.py, session.py       engine, SessionLocal, get_db
│   │   ├── models.py                 las 25 tablas del DBML + tablas técnicas `idempotency_keys` y `llm_llamadas` (trazabilidad del LLM)
│   │   ├── reset.py                  drop + create_all + seed
│   │   └── seed_demo.py              dataset de Pedro (EMP-0001), ver §5
│   ├── schemas/
│   │   ├── common.py                 F0 (B) — enums del contrato, Meta, Error, Dinero
│   │   ├── ingesta.py                A
│   │   ├── movimientos.py            A
│   │   ├── asistente.py              A
│   │   ├── salud.py                  A
│   │   ├── llm_trazas.py             A  (observabilidad del LLM)
│   │   ├── resumen.py                B
│   │   ├── forecast.py               B
│   │   ├── cuentas.py                B  (fiados, pedidos, chequeo, recordatorio)
│   │   ├── simulador.py              B
│   │   ├── analisis.py               B
│   │   └── alertas.py                B
│   ├── routers/                      F0 (B) crea todos como stub con el JSON del mock; luego cada dueño los llena
│   │   ├── webhooks.py               A   POST /webhooks/whatsapp
│   │   ├── ingesta.py                A   POST /ingesta/interpretar · /confirmar · /cuaderno
│   │   ├── media.py                  A   POST /media/subidas (URL prefirmada PUT a Cloudflare R2)
│   │   ├── impuestos.py              A   POST /empresas/{id}/impuestos
│   │   ├── movimientos.py            A   GET/POST /empresas/{id}/movimientos
│   │   ├── asistente.py              A   POST /empresas/{id}/asistente/mensajes
│   │   ├── salud.py                  A   GET /salud · POST /metas
│   │   ├── llm_trazas.py             A   GET /empresas/{id}/llm/llamadas · /llm/resumen (interno; contract.md §11)
│   │   ├── resumen.py                B   GET /resumen
│   │   ├── forecast.py               B   GET /forecast · POST /forecast/ajustes
│   │   ├── fiados.py                 B   GET /fiados · POST /fiados/{id}/recordatorio
│   │   ├── pedidos.py                B   GET /pedidos · POST /pedidos/chequeo
│   │   ├── simulador.py              B   POST /simular
│   │   ├── analisis.py               B   GET /analisis
│   │   ├── alertas.py                B   GET /alertas · POST /alertas/{id}/accion · POST /alertas/evaluar · PUT /preferencias-alertas
│   │   └── health.py                 B   GET /health
│   └── services/
│       ├── ingesta/                  A
│       │   ├── transcriptor.py       faster-whisper local (audio → texto); acepta file://, demo:// y r2://
│       │   ├── almacenamiento.py     Cloudflare R2 (boto3, S3-compatible): presignar_subida, descargar/archivo_temporal (solo r2://empresas/{empresa_id}/…, tipo y tamaño verificados con HEAD)
│       │   ├── llm_client.py         cliente mínimo de OpenRouter (httpx, timeouts, LLMNoDisponible); con `traza` registra cada llamada
│       │   ├── traza_llm.py          trazabilidad: escribe/enlaza filas de `llm_llamadas` (tokens, costo, latencia, estado; imágenes solo como huella)
│       │   ├── llm_consultas.py      listado con cursor y resumen (día/origen) de `llm_llamadas`
│       │   ├── extractor.py          LLM (OpenRouter) con function calling → MovimientoPropuesto; fallback por reglas/regex
│       │   ├── catalogo.py           monto por catálogo + match de alias (productos, clientes, proveedores)
│       │   ├── registrador.py        ★ INTERFAZ A: escribe transacciones + tablas satélite
│       │   ├── cuaderno.py           F1.2 simplificado (OCR/visión o fixture de 2–3 fotos)
│       │   └── idempotencia.py
│       ├── asistente/                A
│       │   ├── orquestador.py        intención → herramientas → respuesta
│       │   ├── herramientas.py       envuelve las funciones de B (§4.2)
│       │   ├── verificador.py        cada cifra de la respuesta debe existir en los resultados de herramientas
│       │   └── plantillas.py         fallback + microexplicaciones fijas
│       ├── salud/                    A   score.py (3 subindicadores), metas.py
│       ├── finanzas/                 B
│       │   ├── __init__.py           ★ INTERFAZ B: re-exporta las funciones públicas (§4.2)
│       │   ├── consultas.py          v_saldo_caja, v_fiados, v_deudas, v_impuestos (a fecha de corte)
│       │   ├── resumen.py            F2
│       │   ├── proyeccion.py         motor de proyección (flujo ordinario LightGBM o baseline naive estacional + pagos con fecha + ajustes)
│       │   ├── forecast.py           GET /forecast y ajustes (usa proyeccion.py)
│       │   ├── modelo_ml.py          carga perezosa/cacheada de los artefactos de ML, diagnóstico y `meta` del motor vigente
│       │   ├── forecast_ml.py        features desde la BD + predicción recursiva del LightGBM + banda
│       │   ├── riesgo.py             riesgo de atraso de fiados (baseline) + recordatorio
│       │   ├── disponible.py         "disponible para gastar"
│       │   ├── chequeo.py            chequeo antes del pedido (F4)
│       │   ├── simulador.py
│       │   └── analisis.py           F5
│       └── alertas/                  B   reglas.py (prioridades 1–4), motor.py (límites diarios, silencio)
└── tests/
    ├── conftest.py                   F0 (A)
    ├── test_a_*.py                   A
    └── test_b_*.py                   B
```

**Regla de oro:** después de la Fase 0, `core/`, `db/models.py`, `schemas/common.py` y `main.py` solo se tocan con un PR pequeño que el otro revisa (5 min). Nadie edita una carpeta del otro.

---

## 4. Contrato interno entre A y B

### 4.1 Lo que A expone (B no lo necesita para trabajar, pero lo usa el seed y los tests)

```python
# services/ingesta/registrador.py
def registrar_movimiento(db, empresa_id: str, mov: MovimientoPropuesto, *,
                         canal: Canal, borrador_id: str | None = None,
                         confianza: Decimal | None = None, fue_corregida: bool = False
                         ) -> RegistroResultado:
    """Crea la transacción, su detalle y la fila satélite que corresponda
    (cuaderno_fiado / deudas / impuestos) según diccionario §4. Hace commit.
    RegistroResultado = {movimiento_id, registros_creados: [{tabla, id}]}"""
```

### 4.2 Lo que B expone (A lo llama desde `confirmar`, el asistente y el score)

Todas reciben `db`, `empresa_id` y opcionalmente `fecha_corte` (por defecto `reloj.hoy()`), y devuelven los **schemas de respuesta del contrato** (pydantic).

```python
# services/finanzas/__init__.py
saldo_caja(db, empresa_id, fecha_corte=None) -> Decimal
fiados(db, empresa_id, estado="pendiente", fecha_corte=None) -> FiadosResponse          # §4.3
pedidos(db, empresa_id, estado="pendiente", fecha_corte=None) -> PedidosResponse        # §4.4
estado_impuestos(db, empresa_id, fecha_corte=None) -> EstadoImpuestos
resumen(db, empresa_id, periodo: str, fecha_corte=None) -> ResumenResponse              # §3
forecast(db, empresa_id, horizonte_dias=30, fecha_corte=None) -> ForecastResponse       # §4.1
chequeo_pedido(db, empresa_id, proveedor, monto, fecha_vencimiento) -> ChequeoResponse  # §4.5
simular(db, empresa_id, acciones: list[Accion]) -> SimulacionResponse                   # §4.6

# services/alertas/__init__.py
evaluar_alertas(db, empresa_id, disparador: str | None = None, entidad_id: str | None = None) -> list[Alerta]  # §6.3
alertas(db, empresa_id, estado="activa") -> AlertasResponse                             # §6.1
```

- En la **Fase 0**, B deja estas funciones escritas devolviendo los JSON del mock del contrato (Pedro: saldo S/ 2 340, déficit −S/ 650 el 30/11, pedido S/ 2 400 a Andina, fiados S/ 310). Desde ese momento A ya puede integrarlas.
- Cambiar una firma = avisar al otro y PR pequeño. Agregar campos opcionales a la respuesta sí se puede sin avisar.

### 4.3 Flujo donde se tocan (el único "cruce" fuerte)

```text
POST /ingesta/confirmar  (A)
  └─ registrador.registrar_movimiento(...)                 (A)  escribe
  └─ si compra a crédito → finanzas.chequeo_pedido(...)    (B)  calcula
  └─ alertas.evaluar_alertas(db, empresa_id, ...)          (B)  calcula y guarda en `alertas`
  └─ finanzas.saldo_caja(...)                              (B)  → saldo_caja_negocio
  ← respuesta 201 con alertas_disparadas
```

La tabla `alertas` la escribe **B** (es salida de su motor). Las tablas `forecast_ajustes` y `preferencias_alertas` también son de B. El resto de escrituras son de A.

---

## 5. Backlog por desarrollador

Prioridad: 🔴 debe estar en la demo · 🟡 versión simplificada.

### Fase 0 — base común (las 2 primeras horas, en paralelo, rama `back/base`)

| Dev A | Dev B |
|---|---|
| `db/models.py`: las 25 tablas del DBML con sus CHECK, únicos e índice parcial del sueldo | Esqueleto: `main.py`, `core/*`, CORS para `localhost:5173`, `/api/v1` |
| `db/session.py`, `get_db`, `reset.py` | `schemas/common.py`: todos los enums del contrato, `Meta`, `ErrorResponse` |
| `seed_demo.py` mínimo: rubro, EMP-0001 "Bodega Don Pedro", categorías, ~20 productos con alias, 3 clientes de fiado, Distribuidora Andina, sueldo programado, ~90 días de ventas sintéticas, deuda PED/DEU de S/ 2 400 al 30/11, fiados por S/ 310, RUS | **Todos** los routers como stub devolviendo el JSON del contrato (copiar de `frontend/src/mocks/data.js`) |
| `tests/conftest.py` con BD de prueba + seed | Interfaces de §4.2 con respuesta mock |

**Checkpoint F0:** merge a `main`. El front puede poner `VITE_USE_MOCK=false` y todo responde (con mocks del backend).

> El seed debe cuadrar con la historia de la demo (context.md §9): saldo 2 340 al 14/11 y faltante de ~650 el 30/11. Si el equipo de datos entrega el dataset sintético, A escribe un cargador desde CSV en lugar del generador mínimo.

### Dev A — Ingesta y conversación

| # | Tarea | Endpoint | Prioridad |
|---|---|---|---|
| A1 | `registrador.py`: todos los casos de diccionario §4 (venta, venta fiada → `cuaderno_fiado`, cobro de fiado, compra a crédito → `deudas`, pago a proveedor, préstamo recibido, retiro personal, gasto, pago de impuesto). Valida los CHECK de `transacciones`. | — | 🔴 |
| A2 | Movimientos: listado con filtros, paginación por cursor y `saldo_post`; registro manual (`canal = manual`, sin borrador) | `GET/POST /empresas/{id}/movimientos` | 🔴 |
| A3 | Extractor de texto: LLM por OpenRouter (`llm_client.py`) con function calling → `MovimientoPropuesto` validado con pydantic. Fallback por reglas (regex de montos, verbos "vendí/saqué/pedí/fié/me pagó"). Monto por catálogo si no se dice. `confianza`, `campos_faltantes`, `pregunta_aclaratoria` si < 0.75. Caso "pagué el colegio" → respuesta de alcance. | `POST /ingesta/interpretar` (texto) | 🔴 |
| A4 | Transcripción de voz con faster-whisper (modelo `small`, CPU) antes del extractor | `POST /ingesta/interpretar` (voz) | 🔴 |
| A5 | Confirmar: aplica `correcciones`, marca borrador, llama a `registrador` y luego a B (§4.3). `204` si se descarta, `409` si ya estaba confirmado. Idempotency-Key. | `POST /ingesta/confirmar` | 🔴 |
| A6 | Pedido a crédito por voz/texto (F1.5): "pedí 2 400 a Andina para el 30" → borrador con proveedor y vencimiento; la respuesta del bot incluye el resultado de `chequeo_pedido` | (dentro de A3/A5) | 🔴 |
| A7 | Webhook del chat simulado: enruta por `empresa_id`/`telefono_hash`, texto/audio → interpretar; botón `confirmar:BOR-x` / `corregir:BOR-x` → confirmar; pregunta → asistente | `POST /webhooks/whatsapp` | 🔴 |
| A8 | Consulta del estado F1.6 ("¿cómo va mi caja?") como primera intención del asistente | `POST /asistente/mensajes` | 🔴 |
| A9 | Impuestos por menú de botones | `POST /empresas/{id}/impuestos` | 🟡 |
| A10 | Asistente F7: intenciones `estado_caja`, `explicar_alerta`, `simular`, `prestamo` + `fuera_de_alcance`. Herramientas = funciones de B. Verificador de cifras → si falla, plantilla. Guarda en `conversaciones`. | `POST /asistente/mensajes` | 🟡 |
| A11 | Cuaderno de fiados: modelo de visión vía OpenRouter (`VLM_MODEL`, `vision.py`, tool call + validación pydantic); fallback a fixture `cuaderno_01..03` o lista vacía con `fallback_usado = true` | `POST /ingesta/cuaderno` | 🟡 |
| A12 | Salud F8 con 3 subindicadores: constancia de registro, separación personal/negocio (retiros vs sueldo), impuestos al día. Historial mensual en `score_salud`. Metas plantilla. | `GET /salud` · `POST /metas` | 🟡 |
| A13 | Set de evaluación del extractor: 100–150 frases con su JSON esperado → script que mide exactitud por campo y % que requiere corrección | `tests/eval_extractor.py` | 🟡 |

### Dev B — Motores financieros

| # | Tarea | Endpoint | Prioridad |
|---|---|---|---|
| B1 | `consultas.py`: saldo de caja, fiados (pendiente, días de atraso, estado), deudas (pendiente, `por_vencer` ≤ 3 días, vencido, pagado), impuestos (al día / vencido). Todo **a fecha de corte** y filtrando `creado_en < fecha_corte`. | — | 🔴 |
| B2 | Resumen F2 con variación vs mes anterior al mismo día de corte; ganancia como rango si faltan costos | `GET /resumen` | 🔴 |
| B3 | Forecast F3: baseline naive estacional (mismo día de la semana, últimas N semanas) + egresos conocidos (deudas, cuotas, sueldo, programados, impuestos) + cobros de fiados ponderados. Banda p10/p50/p90 por residuos. `dia_critico`. Si existe el modelo LightGBM del equipo de ML (`ml/artifacts/`), se usa; si falla → baseline con `fallback_usado = true`. | `GET /forecast` | 🔴 |
| B4 | Disponible para gastar (fórmula del contrato §4.1) con `componentes` y `mensaje` | (dentro de B3) | 🔴 |
| B5 | Ajustes manuales del forecast | `POST /forecast/ajustes` | 🔴 |
| B6 | Fiados con riesgo de atraso: baseline = tasa histórica de atraso del cliente; si existe el clasificador de ML, se usa. Plantilla de recordatorio. | `GET /fiados` · `POST /fiados/{id}/recordatorio` | 🔴 |
| B7 | Pedidos/cuentas por pagar + estado de impuestos | `GET /pedidos` | 🔴 |
| B8 | Chequeo antes del pedido con sugerencias (`reducir_pedido`, `pagar_en_partes`, `combinar`), `fundamento`, `limites`, `confianza` | `POST /pedidos/chequeo` | 🔴 |
| B9 | Simulador determinístico sobre la serie del forecast: `reducir_pedido`, `pagar_en_partes`, `diferir_pago`, `cobrar_fiados`, `limitar_retiros` | `POST /simular` | 🔴 |
| B10 | Motor de alertas, prioridades 1–4: `faltante_caja` (con causas cuantificadas), `pedido_excesivo`, `retiro_excesivo`, `obligacion_proxima` (3 días antes). Límite 2/día, horario silencioso (se guarda con `enviada_en = null`), sin duplicar la misma alerta activa. | `POST /alertas/evaluar` · `GET /alertas` · `POST /alertas/{id}/accion` | 🔴 |
| B11 | Preferencias de alertas | `PUT /preferencias-alertas` | 🔴 |
| B12 | Health con estado de BD, Whisper, LLM y modelos (A le pasa una función `estado_ia()` para Whisper/LLM) | `GET /health` | 🔴 |
| B13 | Análisis F5: 2 agrupaciones (`categoria` y `metodo_pago`) + comparación con pares sintética | `GET /analisis` | 🟡 |
| B14 | Backtest: MAE/MAPE/cobertura del forecast vs baseline y precision/recall de `faltante_caja` contra `saldo_diario.deficit_14d`; los valores alimentan `baseline` y `modelo_metricas` del forecast | `tests/eval_forecast.py` | 🟡 |

#### Estado de Dev B (rama `back/motores`)

Los mocks de la Fase 0 se eliminaron (`app/mocks/` ya no existe): todo B calcula sobre la BD a fecha de corte.

| # | Estado | Notas |
|---|---|---|
| B1 | ✅ real | `consultas.py`: filtra `creado_en`/`fecha_hora` < fin del día de corte (Lima), excluye anuladas, `afecta_caja`; fiados/deudas/impuestos con estados calculados; cronograma de cuotas |
| B2 | ✅ real | variación vs mes anterior al mismo día; ganancia como rango con el margen de los productos con costo |
| B3 | ✅ LightGBM + baseline | flujo ordinario diario con el LightGBM por cuantiles (`FORECAST_MOTOR=lightgbm`, recursivo) + pagos con fecha + ajustes; banda desde los cuantiles del modelo (con piso en su error de 1 paso); día crítico = 1.er día con p50 < 0. Si el modelo no carga, hay < 30 días de historia o `FORECAST_MOTOR=baseline`: naive estacional (4 semanas, banda ±z·σ·√h) con `meta.fallback_usado = true` y `fallback_motivo`. Eval: `tests/eval_forecast.py` compara ambos motores. Fiados ponderados fuera del p50 (en p90, disponible y "Lo que viene"). |
| B4 | ✅ real | `disponible.py` con `componentes` y `mensaje` |
| B5 | ✅ real | `forecast_ajustes`: reemplaza la partida que coincide o suma un egreso extra |
| B6 | ✅ baseline | tasa histórica de atraso del cliente (suavizada); sin clasificador de ML entregado → pendiente de data |
| B7 | ✅ real | pedidos (`por_vencer` ≤ 3 días) + estado de impuestos |
| B8 | ✅ real | venta esperada de los productos del proveedor hasta el vencimiento; no duplica un pedido ya registrado igual |
| B9 | ✅ real | 6 acciones; ventana hasta el día crítico (se alarga si un pago movido cae en el horizonte) |
| B10 | ✅ real | prioridades 1–4, causas cuantificadas, 2/día, silencio, sin duplicar, acción; `GET /alertas` evalúa antes de listar |
| B11 | ✅ real | `PUT /preferencias-alertas` (tabla `preferencias_alertas`) |
| B12 | ✅ real | `forecast` y `credit_scoring` con el estado real del modelo cargado (`ok` / `baseline` / `no_disponible` + motivo); `riesgo_atraso` = `baseline` |
| B13 | 🟡 simplificado | 6 agrupaciones; comparación con pares calculada con empresas del mismo rubro en la BD → `null` en la demo (solo hay 1 bodega): pendiente de data |
| B14 | ✅ | `python -m tests.eval_forecast` (MAE/MAPE/cobertura y precision/recall vs `deficit_14d`) |

Cifras de la demo con el seed (14/11): saldo 2 340 · día crítico 30/11 = −650 (p10 −1 295 / p90 +160) · disponible 0 ·
chequeo 2 400 → [−50, 550, 850] · simular 1 800 + 2 partes → 850 (+ cobrar fiados → 1 160) · alerta `faltante_caja`
650 con causas 700 / 400 / 310. Para cuadrar exacto se ajustó `seed_demo.py`: la calibración deja la proyección de
referencia en −650.00 (antes −649.96) y los pedidos históricos de Andina traen solo cerveza y gaseosa chica (así la
venta esperada de esa mercadería hasta el 30/11 es ≈ S/ 2 000).

**Carga estimada:** A ≈ 13 tareas con más incertidumbre (LLM/Whisper); B ≈ 14 tareas más predecibles (cálculo). Si alguno termina antes, el apoyo natural es: B ayuda a A con A12 (score, que usa sus consultas); A ayuda a B con B13 (análisis).

---

## 6. Checkpoints de integración

| Checkpoint | Qué debe funcionar de punta a punta | Merge a `main` |
|---|---|---|
| **C0** — fin de Fase 0 | Todos los endpoints responden con mocks; BD se crea y siembra con `reset` | Ambos |
| **C1** — registro real | Texto "vendí dos cervezas" → interpretar → confirmar → aparece en `/movimientos` y cambia `saldo_caja` real (B1 hecho) | Ambos |
| **C2** — la historia de Pedro | `/resumen`, `/forecast`, `/fiados`, `/pedidos` con datos reales del seed; "pedí 2 400 a Andina para el 30" dispara `faltante_caja` y `pedido_excesivo` en `alertas_disparadas` | Ambos |
| **C3** — demo completa | Voz, simulador, asistente con 3–4 intenciones, score; front con `VITE_USE_MOCK=false` recorre los 6 pasos de context.md §9 | Ambos |

Antes de cada merge: `pytest` en verde y `python -m app.db.reset` funcionando desde cero.

---

## 7. Mapa de la demo → dueño

| Paso (context.md §9) | Endpoints | Dueño |
|---|---|---|
| 1. Pedro ve su caja (S/ 2 340) y la alerta del 30/11 | `/resumen`, `/forecast`, `/alertas` | B |
| 2. Registra por voz "vendí dos cervezas" | `/ingesta/interpretar`, `/ingesta/confirmar`, `/webhooks/whatsapp` | A (+ B en `alertas_disparadas`) |
| 3. Alerta con causas (700 retiro, 400 pedido, 310 fiados) | `/alertas` | B |
| 4. Simula pedir menos / pagar en 2 partes / cobrar fiados | `/pedidos/chequeo`, `/simular` | B |
| 5. Costo del préstamo informal y alternativas | `/asistente/mensajes` (intención `prestamo`) | A |
| 6. Su score sube | `/salud` | A |

---

## 8. Reglas que ambos deben respetar

- **Nada calculado se guarda** (saldo, pendiente, atraso, estado): siempre se calcula a fecha de corte. Excepción permitida: `alertas`, `score_salud`, `predicciones_*` (son resultados versionados).
- **Nada se borra:** se anula (`anulada = true`).
- `metodo_pago = credito` ⇒ `afecta_caja = false`.
- `pago_tardio`, `deficit_14d`, `eventos` y `clientes.perfil_pago` **nunca** se usan como feature ni en reglas.
- Toda respuesta con salida de modelo lleva `meta`; toda recomendación lleva `fundamento`, `limites` y `confianza`.
- El LLM **no calcula cifras**: solo llama funciones de B.
- Secretos solo en `.env` (y el panel de Render). Contraseñas nunca en texto plano: solo su hash. Datos solo sintéticos.
- Toda ruta nueva se registra con `verificar_acceso` (lo hace `main.py`) y todo campo `*_id` nuevo de un request necesita su
  regla en `core/alcance.py` (`tests/test_e_auth_alcance.py` lo exige).

---

## 9. Lo que falta (al 14/11/2026) y por qué

Estado: A1–A13 y B1–B14 implementados; ~850 tests en verde (incluida la suite sobre `data/csv`). Lo que sigue **no** está hecho o está simplificado. Marcado ✅ = resuelto en la integración con el modelo de datos (rama `feat/integracion-modelo-datos`).

### 9.1 Depende del equipo de data

| Pendiente | Por qué no está | Qué se necesita |
|---|---|---|
| Forecast con LightGBM (B3) ✅ | Integrado: los 6 `.joblib` cargan (carga perezosa y cacheada, validada contra `metadata.json`); `FORECAST_MOTOR=lightgbm` por defecto, con baseline y `meta.fallback_motivo` si no carga, hay < 30 días de historia o falla. Features construidos desde la BD (rubro, `n_trabajadores`, antigüedad, `usa_fiado`/`usa_billetera_digital` = ≥ 1 registro en 90 días, lags/medias/std/calendario como el notebook) sobre el flujo **ordinario**; recursivo; eventos con fecha encima (sin doble conteo). | **Skew conocido** (datos de entrenamiento sintéticos y de otra escala; ver `README.md` §Modelos de ML): en Pedro el modelo subestima su egreso ordinario ≈ 35 % y el MAE del saldo es peor que el baseline; en las 29 empresas con historia queda a la par (933 vs 948 a 7 días). La historia de la demo en `data/csv` se calibra contra el motor final. `usa_billetera_digital` mira `billeteras_digitales`, que el backend no escribe: las ventas con billetera registradas por la app no la activan. |
| Riesgo de atraso de fiados (B6) | No hay artefacto de clasificador. | Entregar el modelo o aceptar el baseline (tasa histórica del cliente). |
| Score de salud con credit scoring (A12) ✅ | Integrado como bloque **adicional** `score_crediticio` en `GET /salud` (no reemplaza el score de 3 hábitos): regresión logística + scaler, 16 features calculados en Python desde el ORM con las definiciones del notebook (las vistas del DBML son comentarios con errores) y propuesta `riesgo_pago_ml` del equipo de datos como nombre de referencia. | Estimación de un modelo entrenado con datos sintéticos, no una evaluación crediticia. Features sin datos se imputan con la media de entrenamiento; `n_alertas_quiebre_stock` es un proxy calculado desde las ventas (el backend no genera `caida_ventas`). `motor_recomendaciones` **no se integra**: sus ideas útiles ya son las reglas `gasto_inusual`, `fiado_vencido` y `meta_lograda`. |
| Comparación con pares (B13) ✅ | El cálculo existe; con solo Pedro daba `comparacion_pares = null`. | Resuelto en local: `python -m app.db.cargar_csv` (o `reset --fuente csv`) carga las 30 empresas de `data/csv/`. |
| Recall de `faltante_caja` (B14) | La historia sintética no tiene ningún día con `deficit_14d` positivo: no se puede medir. | Un dataset con episodios de déficit. |

### 9.2 Dev A — ingesta y conversación

| Pendiente | Por qué |
|---|---|
| Registrar de nuevo "pedí 2 400 a Andina para el 30" crea un segundo pedido (PED-0013) y la alerta sale con faltante 3 050 en vez de 650 (sigue pendiente: varios tests documentan ese comportamiento; con `data/csv` la demo no trae el pedido repetido) | PED-0012 ya está en el seed y `confirmar` no detecta pedidos iguales ya registrados. La demo de 6 pasos no lo registra, pero si se dice en vivo, el número sale mal. Arreglo propuesto: avisar "ya está registrado" si coincide proveedor, monto y vencimiento con una deuda pendiente (como los duplicados del cuaderno). |
| ✅ Pregunta por voz ("¿cómo va mi caja?" en audio) no llegaba al asistente | Resuelto: el webhook transcribe primero y usa el mismo enrutador que el chat (pregunta → asistente, movimiento → registro). |
| ✅ "Dame un reporte" respondía la ayuda genérica | Resuelto: "reporte", "cómo me fue", "cómo van mis ventas" → `estado_caja`. Los chips "Sí/No, salió de la caja" ya no quedan en bucle. |
| Asistente sin function calling del LLM (A10, simplificado) | Decisión del hackathon: la intención se clasifica por regex y cada una tiene un plan fijo de funciones de B; el LLM solo redacta y el verificador descarta cifras inventadas. |
| Foto que no es del cuaderno (boleta, recibo) | Toda imagen se trata como cuaderno de fiados; no hay ruta para comprobantes. |
| Whisper real sin probar (A4) | El código está listo, pero no se descargó el modelo `small` (~480 MB) ni se probó con audio real. |
| VLM probado solo con una imagen sintética (A11) | No hay fotos reales de cuaderno; las fotos no se redimensionan (hasta 8 MB, más latencia). |
| Ruta LLM del extractor sin medir (A13) | `eval_extractor.py --llm` hace 1 llamada por frase; solo se midió el fallback por reglas (84 % de frases exactas en holdout). |
| Anular un movimiento | `anular_movimiento()` existe, pero el contrato no tiene endpoint (sin cambios). |
| Trazas LLM perdidas en errores 500 | Si el request termina en 500 y hace rollback, su fila de `llm_llamadas` se pierde (los errores controlados sí quedan). |

### 9.2.1 Resuelto en la integración con el modelo de datos

- ✅ Categorías canónicas `snake_case` (16) con comparación tolerante y error 400 claro; `seed_demo.py` usa el mismo catálogo y rubros que `data/csv`.
- ✅ Alertas: sin `IndexError` con 1 causa, `entidad_tipo` en plural (acepta singular), render de los 9 tipos, refresco de la alerta activa tras cada movimiento, sueldo mensual/quincenal prorrateado, y reglas nuevas `gasto_inusual`, `fiado_vencido` por cliente y `meta_lograda`.
- ✅ `items[].cantidad` sale como número; `/health` lee las versiones de prompts de las constantes; mensajes de validación en español; `negocio.nombre` en `/resumen`; `pedido_id` en las acciones del asistente.
- ✅ Cargador `python -m app.db.cargar_csv`, `reset --fuente seed|csv` y suite `tests/integracion_csv/` (BD `cajaclara_csv`); la historia de la demo sobre el CSV queda como `xfail` "pendiente de calibración".

### 9.3 Dev B — motores financieros

| Pendiente | Por qué |
|---|---|
| Fiados fuera de la proyección p50 | Decisión para cuadrar la historia (−650 el 30/11); si entraran ponderados daría ≈ −485. Entran en p90, disponible y "Lo que viene". Revisar con el equipo. |
| ✅ `GET /alertas` escribía en la tabla `alertas` (y `GET /salud` en `score_salud`) | Resuelto: los GET calculan sin escribir (alertas pendientes con `persistida = false` e ID estable `ALR-PEND.…`); se guardan en `POST /alertas/evaluar`, al confirmar y al accionar; el score se guarda con `POST /salud/recalcular`. |
| Simulador mide el mínimo solo hasta el día crítico | Si la 2.ª cuota cae dentro del horizonte (p. ej. 10/12), el resultado es −712: el baseline proyecta ≈ −250 por semana. |
| Forecast sobreestima ≈ +200 a 7–14 días | Los pedidos que se hacen después del corte no se pueden prever con el baseline. |

### 9.4 Infraestructura y producción

| Pendiente | Por qué |
|---|---|
| BD de producción (Render) sin esquema | La BD `hackbbva` está vacía (0 tablas). Falta decidir: `python -m app.db.migrar` con `APP_ENV=produccion` (tablas vacías) o además cargar la demo (requiere un paso de carga; `reset` está bloqueado en producción a propósito). |
| Rotar la contraseña de Render | Se compartió en un chat. |
| Despliegue del backend en producción | No está definido dónde corre ni dónde se fija `APP_ENV=produccion`. |
| R2 sin prueba de punta a punta | Las credenciales y el bucket ya están configurados, pero falta probar el PUT desde el navegador, la regla CORS del bucket (`PUT` desde el origen del front con header `Content-Type`) y la regla de vida para borrar audios. El tamaño máximo no va firmado en el PUT (se valida al pedir la URL y con HEAD antes de leer). |
| Cambios de columnas en producción | Sin Alembic: `app.db.migrar` solo crea tablas nuevas; un cambio de columnas en una tabla existente se hace a mano. |
| Login de las demos ✅ | `POST /auth/login` + `GET /auth/sesion`, Bearer con alcance por empresa en todas las rutas, límites de login por IP y de IA por sesión/usuario, CORS para `cclara.site`. Falta en Render: llenar `AUTH_SECRET` y `AUTH_CREDENCIALES` en el panel y agregar `https://cclara.site` y `https://www.cclara.site` a la regla CORS del bucket de R2. Los límites viven en memoria (se pierden al reiniciar; una sola instancia). |
| IP real detrás de Render | Se toma de `CF-Connecting-IP` (`IP_CLIENTE_CABECERA` en `render.yaml`), según la documentación de la comunidad de Render (Cloudflare delante de todos los servicios). Verificar en los logs de Render que los "Login fallido desde <ip>" muestran IPs públicas distintas; si todas son iguales, el límite de login se comparte entre todos. |
| Restaurar una demo ✅ | `python -m app.db.restaurar_demo --empresa EMP-0001` vuelve una empresa al estado de `data/csv` sin tocar las demás ni `llm_llamadas` (bloqueado en producción salvo `--produccion --confirmar <BD>`). |
| Dependencias transitivas sin fijar | `requirements.txt` fija solo las directas; un lock completo saldría de `pip freeze` dentro del contenedor. |

### 9.5 Front (no es del backend, pero lo bloquea en la demo)

- Usar el flujo de subida a R2 (`contract.md` §1.0) en `frontend/src/pages/Chat/media.js` (hoy usa `demo://`).
- Adoptar los cambios de contrato de B: PED-0012 sale `pendiente` (no `por_vencer`), `comparacion_pares` puede ser `null`, la categoría de análisis es `retiro_personal` (antes `retiros_personales`), y campos opcionales nuevos en resumen, chequeo, simulador y análisis.
- Probar con `VITE_USE_MOCK=false` los 6 pasos de la demo (§7).

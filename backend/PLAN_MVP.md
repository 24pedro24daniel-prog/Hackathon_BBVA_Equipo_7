# CajaClara — Plan del backend (MVP) para 2 desarrolladores

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
| Config | `pydantic-settings` (`core/config.py`) lee 3 archivos de `backend/`: **`parametros.env`** (no secretos, versionado: host/puerto/BD, `FECHA_DEMO`, `TZ=America/Lima`, `LLM_*`, `WHISPER_*`, `UMBRAL_CONFIANZA`), **`.env`** (solo credenciales, NO versionado: `POSTGRES_USER`, `POSTGRES_PASSWORD`, `API_KEY`, `OPENROUTER_API_KEY`) y **`example.env`** (plantilla versionada de `.env`). Las variables de entorno reales tienen prioridad. `DATABASE_URL` se compone de las partes (override opcional con `DATABASE_URL`). |
| LLM y voz | LLM por **OpenRouter** (API compatible con OpenAI, `/chat/completions` con `tools`), cliente `httpx` en `services/ingesta/llm_client.py`. Whisper con **faster-whisper local** (`small`, CPU, `int8`), carga perezosa. |
| Docker | `backend/Dockerfile` (`python:3.12.15-slim`, usuario no root) + `docker-compose.yml` (`db` + `backend`, `env_file: [parametros.env, .env]`, volumen de caché de Whisper). |
| Puerto | `uvicorn app.main:app --port 8000` (el front ya proxea `/api` a `localhost:8000`). Prefijo `/api/v1`. |
| Fecha "hoy" | Variable `FECHA_DEMO=2026-11-14` en `.env`: todos los cálculos usan `core/reloj.py::hoy()`, no `date.today()`. Así la demo de Pedro es reproducible. |
| Ramas | `back/base` (Fase 0) → luego `back/ingesta` (A) y `back/motores` (B). Merge a `main` en cada checkpoint (§6). |
| Tests | `pytest` + BD de prueba. Archivos `tests/test_a_*.py` (A) y `tests/test_b_*.py` (B). |

Dependencias (`requirements.txt`, todas con versión exacta `==`): `fastapi`, `uvicorn[standard]`, `python-multipart`, `sqlalchemy` 2.x, `psycopg[binary]` 3.x, `pydantic` 2.x, `pydantic-settings`, `tzdata`, `httpx` (OpenRouter), `faster-whisper`, `pytest`. Opcional para B: `lightgbm`, `pandas`, `joblib`.

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
│   │   ├── auth.py                   dependencia X-API-Key
│   │   ├── errors.py                 handler → formato { "error": {codigo, mensaje, detalles, request_id} }
│   │   ├── ids.py                    nuevo_id(db, Modelo, "MOV", ancho=6) → "MOV-000123"
│   │   ├── meta.py                   construye el bloque `meta` (request_id, latencia, versión, fallback)
│   │   ├── paginacion.py             limit/cursor → next_cursor
│   │   └── reloj.py                  hoy() / ahora() con FECHA_DEMO y zona America/Lima
│   ├── db/                           F0 (A) — compartido, se congela tras F0
│   │   ├── base.py, session.py       engine, SessionLocal, get_db
│   │   ├── models.py                 las 25 tablas del DBML + tabla técnica `idempotency_keys`
│   │   ├── reset.py                  drop + create_all + seed
│   │   └── seed_demo.py              dataset de Pedro (EMP-0001), ver §5
│   ├── schemas/
│   │   ├── common.py                 F0 (B) — enums del contrato, Meta, Error, Dinero
│   │   ├── ingesta.py                A
│   │   ├── movimientos.py            A
│   │   ├── asistente.py              A
│   │   ├── salud.py                  A
│   │   ├── resumen.py                B
│   │   ├── forecast.py               B
│   │   ├── cuentas.py                B  (fiados, pedidos, chequeo, recordatorio)
│   │   ├── simulador.py              B
│   │   ├── analisis.py               B
│   │   └── alertas.py                B
│   ├── routers/                      F0 (B) crea todos como stub con el JSON del mock; luego cada dueño los llena
│   │   ├── webhooks.py               A   POST /webhooks/whatsapp
│   │   ├── ingesta.py                A   POST /ingesta/interpretar · /confirmar · /cuaderno
│   │   ├── impuestos.py              A   POST /empresas/{id}/impuestos
│   │   ├── movimientos.py            A   GET/POST /empresas/{id}/movimientos
│   │   ├── asistente.py              A   POST /empresas/{id}/asistente/mensajes
│   │   ├── salud.py                  A   GET /salud · POST /metas
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
│       │   ├── transcriptor.py       faster-whisper local (audio → texto)
│       │   ├── llm_client.py         cliente mínimo de OpenRouter (httpx, timeouts, LLMNoDisponible)
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
│       │   ├── forecast.py           baseline naive estacional + carga del modelo ML si existe + fallback
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
| A11 | Cuaderno de fiados: OCR/visión sobre 2–3 fotos de prueba (o fixture precalculado con `fallback_usado = true` si no hay modelo de visión) | `POST /ingesta/cuaderno` | 🟡 |
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
- Secretos solo en `.env`. Datos solo sintéticos.

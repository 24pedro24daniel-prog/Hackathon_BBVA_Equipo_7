# TuCaserito — Backend (FastAPI)

FastAPI + SQLAlchemy 2 + PostgreSQL 16. Plan y reparto A/B: [PLAN_MVP.md](PLAN_MVP.md) · Contrato: [../contract.md](../contract.md) · Tablas: [../modelo_datos.dbml](../modelo_datos.dbml).
Todos los datos son sintéticos (Pedro, "Bodega Don Pedro", EMP-0001).

## Configuración (3 archivos)

| Archivo | Qué tiene | ¿Se versiona? |
|---|---|---|
| `parametros.env` | Parámetros no secretos: host/puerto/BD, `FECHA_DEMO=2026-11-14`, `TZ`, `LLM_*` (OpenRouter, incluida la trazabilidad `LLM_TRAZA_*`), `WHISPER_*`, `UMBRAL_CONFIANZA`, `R2_ACCOUNT_ID`, `R2_BUCKET`, `MEDIA_*` | Sí |
| `.env` | Solo credenciales: `POSTGRES_USER`, `POSTGRES_PASSWORD`, `API_KEY`, `OPENROUTER_API_KEY`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY` | **No** (`.gitignore`) |
| `example.env` | Plantilla de `.env` con valores vacíos | Sí |

```bash
cd backend
cp example.env .env        # Windows: copy example.env .env — y llena los valores (el archivo explica cómo generarlos)
```

- `API_KEY` es obligatoria: todas las rutas salvo `/health` exigen `X-API-Key`. Ponla también en `frontend/.env` como `VITE_API_KEY`.
- Sin `OPENROUTER_API_KEY` el backend funciona igual; el extractor y el asistente usarán su fallback.

## Audios y fotos en Cloudflare R2

El front sube el archivo directo a R2 con una URL prefirmada (`POST /api/v1/media/subidas`, ver `../contract.md` §1.0) y manda
`media_url = "r2://..."` a `/ingesta/interpretar`, `/ingesta/cuaderno` o al webhook. Sin R2 configurado el backend funciona
igual (los `demo://` y `file://` siguen sirviendo); `POST /media/subidas` responde `503` y `/health` marca `almacenamiento: sin_configurar`.

1. Cloudflare > R2 > **Create bucket** (p. ej. `cajaclara-media`, privado; no actives el acceso público).
2. R2 > **Manage R2 API Tokens** > Create API token: permiso **Object Read & Write**, limitado a ese bucket. Copia el
   *Access Key ID* y el *Secret Access Key* (solo se muestran una vez).
3. **CORS** del bucket (Settings > CORS policy), para que el navegador pueda hacer el `PUT`:
   ```json
   [{"AllowedOrigins": ["http://localhost:5173"], "AllowedMethods": ["PUT"], "AllowedHeaders": ["Content-Type"], "MaxAgeSeconds": 3600}]
   ```
4. Opcional: **Object lifecycle rule** que borre objetos tras N días (los audios son datos personales).
5. `.env`: `R2_ACCESS_KEY_ID=...` y `R2_SECRET_ACCESS_KEY=...`. `parametros.env`: `R2_ACCOUNT_ID=<Account ID de R2 Overview>`
   y `R2_BUCKET=<nombre del bucket>` (también `R2_PRESIGN_TTL_S`, `MEDIA_MAX_AUDIO_BYTES`, `MEDIA_MAX_IMAGEN_BYTES`, `MEDIA_TIPOS_*`).
6. `docker compose up -d --force-recreate backend` y revisa `GET /api/v1/health` (`almacenamiento.estado = ok`).

## Levantar con Docker (recomendado)

```bash
docker compose up -d                                    # db (postgres:16.14) + backend en http://localhost:8000
docker compose run --rm backend python -m app.db.reset  # borra, crea las tablas y siembra la demo de Pedro
curl http://localhost:8000/api/v1/health                # pública
curl -H "X-API-Key: <tu API_KEY>" http://localhost:8000/api/v1/empresas/EMP-0001/resumen
```

- Docs interactivas: <http://localhost:8000/docs>.
- Postgres queda publicado en el host como **`localhost:5433`** (el 5432 puede estar ocupado por un PostgreSQL nativo);
  dentro de compose el backend usa `db:5432`. La primera vez se crea también la BD de pruebas `cajaclara_test`.
- `app/` y `tests/` están montados en el contenedor: tras cambiar código, `docker compose restart backend`.
  Si cambias `requirements.txt`: `docker compose build backend`.
- El modelo de Whisper (`small`) se descarga en la primera transcripción y queda en el volumen `whisper_models`.

## Sin Docker para el backend

Python 3.12+, con la BD levantada (`docker compose up -d db`) en `localhost:5433`:

```bash
python -m venv .venv
.venv\Scripts\activate          # Mac/Linux: source .venv/bin/activate
pip install -r requirements.txt
python -m app.db.reset
uvicorn app.main:app --port 8000 --reload
```

Front contra este backend: en `frontend/.env` poner `VITE_USE_MOCK=false` y `VITE_API_KEY` = `API_KEY` del `.env` del backend.

## Observabilidad del LLM

Cada llamada al LLM/VLM (extractor, asistente, cuaderno) deja una fila en la tabla técnica `llm_llamadas`, también si
falla (timeout, HTTP 4xx/5xx, respuesta inválida, sin API key). Se pide el uso a OpenRouter (`usage.include`).

- **Qué se guarda:** origen, `prompt_version`, modelo solicitado y respondido, `generation_id`, tokens, `costo_usd`,
  latencia, `estado`/`http_status`/`error`, `request` (messages, tools, temperature...), `respuesta` cruda (content,
  tool_calls, finish_reason) y `resultado_uso` (`aceptada`, `rechazada_validacion`, `rechazada_verificador`). La
  llamada se enlaza con el `borrador_id` o el `mensaje_id` que produjo (`referencia_tipo` / `referencia_id`).
- **Privacidad:** nunca se guardan headers ni la API key; las fotos del cuaderno se guardan solo como
  `{"imagen": {"sha256", "bytes", "mime"}}`, jamás el base64. Con `LLM_TRAZA_GUARDAR_CONTENIDO=false` tampoco se guardan
  los `messages` ni el `content` (solo metadatos, tokens y costo); con `LLM_TRAZA_ACTIVA=false` no se escribe nada.
  El texto del usuario sí queda en `request` cuando se guarda el contenido: tratar la tabla como dato sensible.
- **Robustez:** la traza usa la misma sesión que el consumidor (flush, sin commit propio) y va en un SAVEPOINT; si falla
  el guardado solo se registra un warning. Si el flujo termina en error controlado (p. ej. 422 `NO_INTERPRETABLE`) la
  fila se confirma antes; si el request revienta con 500 se pierde con el rollback. Sin `db` (scripts, tests sin BD)
  no se registra nada.
- **Consulta (X-API-Key, uso interno, ver contract.md §11):**

```bash
curl -H "X-API-Key: $API_KEY" "http://localhost:8000/api/v1/empresas/EMP-0001/llm/llamadas?origen=asistente&limit=20"
curl -H "X-API-Key: $API_KEY" "http://localhost:8000/api/v1/empresas/EMP-0001/llm/resumen?desde=2026-11-01"
```

El resumen da, por día y por origen: llamadas, ok/errores, % fallback, tokens, `costo_usd` y latencia p50/p95.

## Tests

```bash
docker compose run --rm backend pytest -q               # dentro de docker
pytest -q                                               # o con el venv
```

- Los tests usan **solo** `cajaclara_test`: la recrean y siembran una vez por sesión y cada test corre en una
  transacción que se revierte. Si Postgres no está accesible, los tests de BD se saltan con un aviso y el resto corre.
- El LLM y Whisper nunca se llaman de verdad en los tests (fixtures `llm_falso` y `whisper_falso` en `tests/conftest.py`).
- La API key de los tests es fija (`tests/conftest.py`); nunca se usan las credenciales de `.env`.
- Convención: `tests/test_a_*.py` (Dev A: BD, seed, ingesta) y `tests/test_b_*.py` (Dev B: core, routers, motores).

## Estado

- Todos los endpoints calculan sobre la BD (ya no hay mocks en el backend).
- BD real: las 25 tablas del DBML (`app/db/models.py`) y el seed de la demo (`app/db/seed_demo.py`). El seed cuadra
  con la historia: caja S/ 2 340 al 14/11, pedido PED-0012 de S/ 2 400 a Distribuidora Andina que vence el 30/11,
  fiados pendientes S/ 310 y retiros +S/ 700 sobre lo usual; la proyección de referencia documentada en el
  módulo da −S/ 650.00 exacto el 30/11.
- `/health` consulta la BD de verdad.
- Interfaces congeladas entre devs: `app/services/finanzas/__init__.py` y `app/services/alertas/__init__.py` (B);
  `app/services/ingesta/registrador.py` (A).

### Dev A (ingesta y conversación) — ya con BD real

`/webhooks/whatsapp`, `/ingesta/*`, `/media/subidas`, `/movimientos`, `/impuestos`, `/asistente/mensajes`, `/salud` y
`/metas` ya no son stub. Los cálculos de B (saldo, forecast, chequeo, simulador, alertas) se llaman solo por su interfaz
(`app/services/finanzas`, `app/services/alertas`).

- Extractor: LLM (OpenRouter, tool forzada) con fallback por reglas (`app/services/ingesta/reglas.py`) si no hay key,
  hay timeout o la salida es inválida (`meta.fallback_usado = true`). Montos siempre del usuario o del catálogo.
- Voz: `media_url` acepta `r2://` (solo claves de la empresa; ver sección R2) o archivos dentro de `MEDIA_DIR` (`file://data/...`, `demo://...`); si no hay archivo y el
  cliente manda `texto` (notas de voz demo del front), se usa ese texto como transcripción.
- Cuaderno de fiados: la foto se lee con un modelo de visión vía OpenRouter (`VLM_MODEL`, por defecto
  `openai/gpt-4o-mini`; misma `OPENROUTER_API_KEY`; `VLM_TIMEOUT_S`, `VLM_MAX_TOKENS`; tamaño máximo
  `MEDIA_MAX_IMAGEN_BYTES`). La imagen se envía al proveedor como data URL base64 (privacidad: sale del servidor).
  Los clientes se emparejan por alias, las líneas tachadas no se proponen y las fechas sin año o relativas se resuelven
  con la fecha de hoy. Si el VLM falla o no hay key se usa el fixture por foto (`cuaderno_01..03`) o una lista vacía,
  con `fallback_usado = true`. Foto de demo real: `demo://fotos/cuaderno_sintetico_01.jpg` (en `data/fotos/`;
  tras agregar fotos nuevas hay que reconstruir la imagen: `docker compose build backend`).
- Evaluación del extractor: `docker compose run --rm backend python -m tests.eval_extractor` (offline, reglas);
  `--llm` agrega la ruta LLM (1 llamada a OpenRouter por frase).

### Dev B (motores financieros) — con BD real

`/resumen`, `/forecast`, `/forecast/ajustes`, `/fiados`, `/fiados/{id}/recordatorio`, `/pedidos`, `/pedidos/chequeo`,
`/simular`, `/analisis`, `/alertas`, `/alertas/{id}/accion`, `/alertas/evaluar`, `/preferencias-alertas` y `/health`
(componentes `forecast` y `riesgo_atraso`). Código en `app/services/finanzas/` y `app/services/alertas/`; detalle de cada
regla en el docstring de su módulo y en `../contract.md`.

- **A fecha de corte:** todo se calcula al responder con lo registrado (`creado_en`) y ocurrido (`fecha_hora`) antes del
  fin del día de corte en Lima, sin lo anulado; lo fiado o pedido a crédito no mueve caja. Nada calculado se guarda;
  solo B escribe `alertas`, `forecast_ajustes` y `preferencias_alertas`.
- **Forecast:** baseline naive estacional (mismo día de la semana, últimas 4 semanas) + pagos con fecha (deudas y cuotas,
  luz/sueldo programados, impuestos) + ajustes manuales; banda p10/p90 por residuos. Los fiados ponderados por su
  probabilidad de pago van a `cobros_esperados`, a la banda optimista y a "Lo que viene", **no** a la línea esperada:
  cobrar a tiempo es incierto y es la palanca "cobrar fiados" del simulador (si entraran, el 30/11 de Pedro pasaría de
  −650 a ≈ −485).
- **Alertas:** `GET /alertas` evalúa las 4 reglas antes de listar (sin duplicar). Máx. 2 notificadas al día y horario
  silencioso: las que no se notifican se guardan con `enviada_en = null` (corre la demo fuera de 21:00–07:00 si quieres
  verlas como enviadas).

### Modelos de ML (equipo de datos)

Los artefactos viven fuera del contexto del build, en `../modelo/artifacts/` (`prediccion_ingreso_egreso/` LightGBM por cuantiles,
`credit_scoring/` regresión logística). `docker-compose.yml` los monta **solo lectura** en `/app/ml/artifacts` y fija
`ML_ARTIFACTS_DIR=/app/ml/artifacts`; fuera de docker `ML_ARTIFACTS_DIR` vacío (en `parametros.env`) resuelve a
`../modelo/artifacts`.

- Regla: un modelo se integra solo si sus artefactos cargan y **todos** sus features se pueden construir desde la BD
  sin inventar valores. `app/services/finanzas/modelo_ml.py` lo verifica leyendo solo `metadata.json` (sin dependencias
  de ML, cacheado) y `/health` lo reporta (`forecast.estado = "baseline"`, `forecast.ml.motivo`).
- **Forecast LightGBM: no integrable hoy.** Los 6 `.joblib` sí deserializan (probado aparte con lightgbm 4.7.0 /
  scikit-learn 1.9.1, sin warnings; la imagen slim necesitaría además `libgomp1`), pero 4 de sus 27 features no existen
  en la BD: `rubro` (el modelo espera abarrotes/bebidas/mixto/panaderia; la BD tiene bodega/restaurante/…), `zona`
  (urbano/periurbano/rural vs. texto libre "SJL"), `usa_fiado` y `usa_billetera_digital` (banderas fijas del simulador
  del notebook). Por eso no se agregaron `lightgbm`/`scikit-learn`/`pandas` a `requirements.txt` y el forecast responde
  con el baseline (`meta.fallback_usado = true`, `meta.fallback_motivo`). Para integrarlo hace falta que datos defina
  esos 4 features para una bodega real (o reentrene sin ellos) y documente qué tipos de movimiento cuentan como
  `ingreso`/`egreso`.
- **Riesgo de atraso:** no hay clasificador en `modelo/artifacts/`; se usa la tasa histórica de atraso del cliente.
- **Credit scoring** (`credit_scoring/`): es de Dev A (score de salud); B no lo integra.

### Backtest del forecast (B14)

```bash
docker compose run --rm backend python -m tests.eval_forecast              # BD de desarrollo, solo lectura
docker compose run --rm backend python -m tests.eval_forecast --test --json --horizonte 7
```

Para cada día de corte con ≥ 4 semanas de historia proyecta con lo que se sabía ese día y compara con lo que pasó:
MAE / MAPE / sesgo / cobertura p10–p90 del saldo por horizonte (vs persistencia), MAE del flujo diario (vs "igual que
ayer") y precision / recall de `faltante_caja` contra `saldo_diario.deficit_14d` (etiqueta solo para evaluar, nunca
feature). Con el seed de Pedro (49 cortes, horizonte 14): MAE del saldo 87 a 1 día y ≈ 233 a 14 días (persistencia
155 / 267), cobertura p10–p90 0.57–0.82, sesgo positivo ≈ +200 a 7–14 días (los pedidos de Andina que aún no se habían
hecho al corte no se pueden prever) y MAE del flujo diario 45 vs 172 de "igual que ayer". La historia sintética no
tiene días con déficit a 14 días, así que el recall del faltante no es medible (0 falsas alarmas en 49 cortes).


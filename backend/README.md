# TuCaserito — Backend (FastAPI)

FastAPI + SQLAlchemy 2 + PostgreSQL 16. Plan y reparto A/B: [PLAN_MVP.md](PLAN_MVP.md) · Contrato: [../contract.md](../contract.md) · Tablas: [../modelo_datos.dbml](../modelo_datos.dbml).
Todos los datos son sintéticos (Pedro, "Bodega Don Pedro", EMP-0001).

## Configuración (3 archivos)

| Archivo | Qué tiene | ¿Se versiona? |
|---|---|---|
| `parametros.env` | Parámetros no secretos: host/puerto/BD, `FECHA_DEMO=2026-11-14`, `TZ`, `CORS_ORIGINS`, `AUTH_USUARIOS` (usuario interno → empresa), `AUTH_TOKEN_TTL_S`, límites `AUTH_LOGIN_*` / `AUTH_IA_*`, `IP_CLIENTE_CABECERA`, `LLM_*` (OpenRouter, incluida la trazabilidad `LLM_TRAZA_*`), `WHISPER_*`, `UMBRAL_CONFIANZA`, `R2_ACCOUNT_ID`, `R2_BUCKET`, `MEDIA_*` | Sí |
| `.env` | Solo credenciales: `POSTGRES_USER`, `POSTGRES_PASSWORD`, `API_KEY`, `OPENROUTER_API_KEY`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `DATABASE_URL_PRODUCCION`, `AUTH_SECRET`, `AUTH_CREDENCIALES` | **No** (`.gitignore`) |
| `example.env` | Plantilla de `.env` con valores vacíos | Sí |

```bash
cd backend
cp example.env .env        # Windows: copy example.env .env — y llena los valores (el archivo explica cómo generarlos)
```

- Todas las rutas salvo `/health` y `POST /auth/login` exigen `Authorization: Bearer <token>` (login de las demos, ver
  abajo) o `X-API-Key` (= `API_KEY`, para el bot y la administración). El front **ya no** lleva la API key.
- Sin `OPENROUTER_API_KEY` el backend funciona igual; el extractor y el asistente usarán su fallback.

## Login de las demos (Bearer)

Contrato: [`../contract.md`](../contract.md) §12. Tres usuarios fijos (sin registro): el login devuelve un token firmado
(HS256 con `AUTH_SECRET`, 8 h) que solo sirve para **su** empresa (`403 EMPRESA_NO_PERMITIDA` si el path, la query o el
body apuntan a otra). Las contraseñas nunca están en el repo: `AUTH_CREDENCIALES` guarda su hash scrypt con sal.

```bash
curl -s -X POST http://localhost:8000/api/v1/auth/login -H "Content-Type: application/json"      -d '{"usuario": "<usuario>", "contrasena": "<contraseña>"}'          # → {"token", "empresa_id", "negocio", …}
curl -H "Authorization: Bearer <token>" http://localhost:8000/api/v1/auth/sesion
curl -H "Authorization: Bearer <token>" http://localhost:8000/api/v1/empresas/EMP-0001/resumen
```

| Dónde | Qué |
|---|---|
| `parametros.env` | `AUTH_USUARIOS=USR-01:EMP-0001,USR-02:EMP-0030,USR-03:EMP-0002` (usuario interno → empresa; para cambiar la empresa de una demo se cambia aquí). `USR-01` = login de la demo de Pedro (EMP-0001), `USR-02` = la bodega sana (EMP-0030 Bodega SurAndina), `USR-03` = la bodega del día 3 (EMP-0002) |
| `.env` / panel de Render | `AUTH_SECRET` (≥ 32 caracteres aleatorios: `python -c "import secrets; print(secrets.token_urlsafe(48))"`) y `AUTH_CREDENCIALES` = `USR-01:<login>:<hash>,USR-02:<login>:<hash>,USR-03:<login>:<hash>`. El login va en la credencial (no en `parametros.env`) porque en las demos coincide con la contraseña |

Generar el hash de una contraseña (scrypt n=2^14, r=8, p=1, sal de 16 bytes; ~50 ms en local, ~0,5 s en el plan free
de Render):

```bash
python -m app.core.claves_demo --usuario USR-02 --login <login>     # pide la contraseña sin mostrarla → USR-02:<login>:<hash>
python -m app.core.claves_demo <contraseña>                         # solo el hash (queda en el historial de la terminal)
docker compose run --rm backend python -m app.core.claves_demo --usuario USR-02 --login <login>   # lo mismo en docker
```

Solo usa la stdlib: corre también fuera de docker desde `backend/`. Cambiar `AUTH_SECRET` cierra todas las sesiones;
cambiar la empresa de un usuario en `AUTH_USUARIOS` invalida sus tokens.

**Límites (en memoria, una instancia):** 10 logins fallidos por IP en 10 min → `429 DEMASIADOS_INTENTOS` con
`Retry-After`. Con Bearer, las rutas que gastan LLM/VLM/Whisper/R2 (`/ingesta/interpretar`, `/ingesta/cuaderno`,
`/media/subidas`, `/webhooks/whatsapp`, `/chat/mensajes`, `/asistente/mensajes`) admiten 60 usos por sesión y 200 por
usuario por hora (`AUTH_IA_*`); la `X-API-Key` no tiene límite. La IP del cliente sale de la conexión TCP (local; uvicorn
corre con `--no-proxy-headers` y `X-Forwarded-For` nunca se lee) o de `IP_CLIENTE_CABECERA` detrás de un proxy de
confianza (Render: `CF-Connecting-IP`, que Cloudflare sobreescribe).

### Despliegue en Render (panel > Environment)

`render.yaml` ya fija `APP_ENV`, `PORT`, `WHISPER_MODEL`, `CORS_ORIGINS=http://localhost:5173,https://cclara.site,https://www.cclara.site,https://tucaserito.vercel.app`,
`IP_CLIENTE_CABECERA=CF-Connecting-IP` y `FORECAST_MOTOR`. En el panel se llenan (mismos valores que `backend/.env`):
`DATABASE_URL_PRODUCCION`, `API_KEY`, `OPENROUTER_API_KEY`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY` y las **nuevas**
`AUTH_SECRET` y `AUTH_CREDENCIALES`. Sin ellas `POST /auth/login` responde `503` (el resto de la API sigue con
`X-API-Key`). El front ya no es un static site de Render: va en Vercel con el dominio `cclara.site`.

## Audios y fotos en Cloudflare R2

El front sube el archivo directo a R2 con una URL prefirmada (`POST /api/v1/media/subidas`, ver `../contract.md` §1.0) y manda
`media_url = "r2://..."` a `/ingesta/interpretar`, `/ingesta/cuaderno` o al webhook. Sin R2 configurado el backend funciona
igual (los `demo://` y `file://` siguen sirviendo); `POST /media/subidas` responde `503` y `/health` marca `almacenamiento: sin_configurar`.

1. Cloudflare > R2 > **Create bucket** (p. ej. `cajaclara-media`, privado; no actives el acceso público).
2. R2 > **Manage R2 API Tokens** > Create API token: permiso **Object Read & Write**, limitado a ese bucket. Copia el
   *Access Key ID* y el *Secret Access Key* (solo se muestran una vez).
3. **CORS** del bucket (Settings > CORS policy), para que el navegador pueda hacer el `PUT`:
   ```json
   [{"AllowedOrigins": ["http://localhost:5173", "https://cclara.site", "https://www.cclara.site"], "AllowedMethods": ["PUT"], "AllowedHeaders": ["Content-Type"], "MaxAgeSeconds": 3600}]
   ```
4. Opcional: **Object lifecycle rule** que borre objetos tras N días (los audios son datos personales).
5. `.env`: `R2_ACCESS_KEY_ID=...` y `R2_SECRET_ACCESS_KEY=...`. `parametros.env`: `R2_ACCOUNT_ID=<Account ID de R2 Overview>`
   y `R2_BUCKET=<nombre del bucket>` (también `R2_PRESIGN_TTL_S`, `MEDIA_MAX_AUDIO_BYTES`, `MEDIA_MAX_IMAGEN_BYTES`, `MEDIA_TIPOS_*`).
6. `docker compose up -d --force-recreate backend` y revisa `GET /api/v1/health` (`almacenamiento.estado = ok`).

## Levantar con Docker (recomendado)

```bash
docker compose up -d                                    # db (postgres:16.14) + backend en http://localhost:8000
docker compose run --rm backend python -m app.db.reset  # borra, crea las tablas y siembra la demo de Pedro
docker compose run --rm backend python -m app.db.reset --fuente csv   # igual, pero cargando data/csv (30 empresas)
curl http://localhost:8000/api/v1/health                # pública
curl -H "X-API-Key: <tu API_KEY>" http://localhost:8000/api/v1/empresas/EMP-0001/resumen   # o con Bearer (ver arriba)
```

- Docs interactivas: <http://localhost:8000/docs>.
- Postgres queda publicado en el host como **`localhost:5433`** (el 5432 puede estar ocupado por un PostgreSQL nativo);
  dentro de compose el backend usa `db:5432`. La primera vez se crea también la BD de pruebas `cajaclara_test`.
- `app/` y `tests/` están montados en el contenedor: tras cambiar código, `docker compose restart backend`.
  Si cambias `requirements.txt` o `constraints.txt`: `docker compose build backend` (ver [Dependencias](#dependencias)).
- El modelo de Whisper (`small`) se descarga en la primera transcripción y queda en el volumen `whisper_models`.

## Cargar `data/csv` (local igual a producción)

Producción (Render) se carga desde `data/csv`; local puede hacer lo mismo con el cargador, que crea el esquema de
`app/db/models.py` y carga cada CSV en orden de llaves foráneas (convierte json, bool, decimal y timestamptz y valida
los conteos):

```bash
docker compose run --rm backend python -m app.db.cargar_csv                 # BD principal (POSTGRES_DB), la recrea
docker compose run --rm backend python -m app.db.cargar_csv --bd cajaclara_csv   # otra BD local (se crea si no existe)
docker compose run --rm backend python -m app.db.reset --fuente csv         # lo mismo vía reset (seed | csv)
```

- La carpeta sale de `DATA_CSV_DIR` (`parametros.env`): en docker es `/app/data_csv` (`../data/csv` montado solo lectura);
  fuera de docker, vacío = `../data/csv`. `--dir` la cambia por ejecución.
- No falla en silencio: imprime las columnas del CSV que `models.py` no tiene (se ignoran), las columnas de `models.py`
  que el CSV no trae, los CSV sin tabla y las tablas sin CSV. Un conteo distinto o un valor que no se convierte termina
  con error (código 1).
- **Bloqueado en producción** igual que `reset` (`APP_ENV=produccion` o la URL de `DATABASE_URL_PRODUCCION`): termina con
  código 2. Solo se salta con `--produccion --confirmar hackbbva` (existe para cargar Render a propósito; no se usa desde
  tests ni desde el flujo normal).
- `seed_demo.py` queda como fixture de los tests unitarios (BD `cajaclara_test`) y usa los mismos catálogos que el CSV
  (16 categorías `snake_case`, rubros bodega/restaurante/taller/distribuidora).

## Restaurar una empresa después de una demo en vivo

Una demo en vivo registra movimientos de verdad. Para volver UNA empresa a su estado de `data/csv` sin tocar las demás:

```bash
docker compose run --rm backend python -m app.db.restaurar_demo --empresa EMP-0001                 # BD principal
docker compose run --rm backend python -m app.db.restaurar_demo --empresa EMP-0001 --bd cajaclara_csv
python -m app.db.restaurar_demo --empresa EMP-0001 --produccion --confirmar <nombre de la BD de producción>   # Render
```

- En una transacción: borra **solo** las filas de esa empresa en todas las tablas (hijas primero; `detalle_transaccion` y
  `predicciones_fiado`, que no tienen `empresa_id`, por la llave a su padre; también sus `idempotency_keys`) y vuelve a
  insertar solo sus filas de los CSV, con la misma conversión de tipos que `cargar_csv`. La fila de `empresas` se
  actualiza en su lugar; `rubros`, `categorias`, `llm_llamadas` (trazas de IA) y las otras empresas no se tocan.
- Valida los conteos (los de la BD tienen que ser los del CSV) y si algo falla no cambia nada.
- **Bloqueado en producción** como `cargar_csv` (`APP_ENV=produccion` o la URL de `DATABASE_URL_PRODUCCION`, código 2);
  solo corre con `--produccion --confirmar <nombre de la BD de producción>`. Se corre desde una máquina con
  `DATABASE_URL_PRODUCCION` en `.env`.

## Sin Docker para el backend

Python 3.12+, con la BD levantada (`docker compose up -d db`) en `localhost:5433`:

```bash
python -m venv .venv
.venv\Scripts\activate          # Mac/Linux: source .venv/bin/activate
pip install -r requirements.txt -c constraints.txt
python -m app.db.reset
uvicorn app.main:app --port 8000 --reload --no-proxy-headers
```

Front contra este backend: en `frontend/.env` poner `VITE_USE_MOCK=false` y entrar con un usuario de demo (el front manda
`Authorization: Bearer`; ya no usa `VITE_API_KEY`).

## Dependencias

Todas con versión exacta, en dos archivos:

- `requirements.txt`: solo las **directas** (`==`).
- `constraints.txt`: las **transitivas** congeladas (generado por `tests/congelar_dependencias.py`). El Dockerfile instala
  con `pip install -r requirements.txt -c constraints.txt` y luego `pip check`, así local y Render traen exactamente lo
  mismo. Como el contexto de build es la raíz, el `.dockerignore` de la raíz deja pasar todo `backend/` (incluido este archivo).
- `tests/test_f_dependencias.py` rompe la suite si la imagen tiene un paquete sin fijar o con otra versión, si alguna
  línea no usa `==` o si una directa aparece también en `constraints.txt`.

Subir una versión: cámbiala en `requirements.txt` (o la línea puntual en `constraints.txt`), `docker compose build backend`
y la suite. Si la resolución cambia (paquete nuevo o choque con `constraints.txt`), regenera las transitivas de cero en un
contenedor limpio (desde `backend/`; escribe `constraints.txt` en UTF-8 aunque la terminal sea PowerShell):

```bash
docker run --rm -v "${PWD}:/w" -w /w python:3.12.15-slim sh -c "pip install -q --root-user-action=ignore -r requirements.txt && python tests/congelar_dependencias.py > constraints.txt"
# Git Bash: MSYS_NO_PATHCONV=1 docker run --rm -v "$(pwd -W):/w" -w /w ...   (mismo comando)
```

### Notas de voz: `av` fijado en 18.1.0

faster-whisper decodifica el audio con PyAV (`av`, que trae su propio FFmpeg: la imagen no necesita `ffmpeg`).
faster-whisper 1.2.1 declara solo `av>=11`, pero llama a `av.open(..., metadata_errors="ignore")` y **av 19 quitó ese
argumento**: con av 19.0.2 (lo que instalaba pip sin fijar) toda nota de voz real fallaba con
`TypeError: open() got an unexpected keyword argument 'metadata_errors'` y el usuario veía "Ahora no puedo escuchar
audios" (solo funcionaba si el cliente mandaba el texto). `av==18.1.0` es la última versión que acepta el argumento.

- Formatos probados (decodificación y transcripción real): `audio/webm;codecs=opus` (Chrome/Edge/Firefox, también sin
  cues ni duración como lo graba MediaRecorder), `audio/ogg;codecs=opus` (Firefox, WhatsApp), `audio/mp4` AAC normal y
  fragmentado (Safari) y WAV. Notas de prueba en `tests/datos/audio/` (TTS sintético).
- `tests/test_f_audio.py`: los tests baratos codifican audio en memoria con PyAV y lo decodifican con
  `faster_whisper.audio.decode_audio` (sin cargar Whisper); el test caro transcribe de verdad las 3 notas con
  `servicio.transcribir` y el modelo de `WHISPER_MODEL`, y se salta (con el comando para descargarlo) si el modelo no
  está en `WHISPER_CACHE_DIR`. No subas `av` sin correrlos.
- RAM con Whisper `base` (Render), medida en la imagen con un límite de 512 MiB sin swap y el uvicorn real (resumen,
  forecast LightGBM, salud y 12 notas de voz): ≈ 195 MiB tras arrancar, **pico ≈ 479 MiB** del contenedor al cargar el
  modelo (transitorio, ≈ 465 MiB anónimos) y ≈ 340–357 MiB estable después; sin OOM. Entra en el plan free, con poco
  margen durante la carga (VmRSS del proceso: 450 MiB estable, 540 MiB de pico, contando ≈ 128 MiB de librerías
  compartidas que el kernel puede liberar). `small` no entra en 512 MB.

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
- La API key de los tests es fija (`tests/conftest.py`) y el login usa un `AUTH_SECRET` y usuarios de prueba
  (`tests/_e_util.py`); nunca se usan las credenciales de `.env`.
- Convención: `tests/test_a_*.py` (Dev A: BD, seed, ingesta), `tests/test_b_*.py` (Dev B: core, routers, motores),
  `tests/test_c_*.py` (sincronización con el modelo de datos) y `tests/test_e_*.py` (login, alcance por empresa,
  límites, CORS y `restaurar_demo`). `test_e_auth_alcance.py` recorre todas las rutas: una ruta nueva sin el alcance por
  empresa, o un campo `*_id` nuevo en un request sin regla de verificación, rompe la suite.
- **Suite sobre el CSV** (`tests/integracion_csv/`, marcador `csv`): crea con el cargador la BD dedicada `cajaclara_csv`
  (`POSTGRES_CSV_DB` la cambia) desde `DATA_CSV_DIR` y prueba la API sobre la misma data que producción: registrar cada
  tipo de movimiento, la meta `sueldo_fijo`, y alertas, forecast, resumen, fiados, pedidos, chequeo, simular, salud y
  análisis de las 30 empresas, además de que los GET no escriben (cuenta filas antes y después). Corre con la suite
  normal (`pytest -q`); si no hay CSV o Postgres, se salta con un mensaje. Solo ella: `pytest -m csv -q`. También
  verifica las 3 demos con el LightGBM (context.md §9): Pedro (EMP-0001: saldo 2 340, ≈ −650 el 30/11, causas 700/400/310,
  chequeo −50/550/850, 1 800 en 2 partes → 850; tras la venta en vivo de S/ 13 el faltante baja 13), la bodega sana
  EMP-0030 (sin día crítico y con margen) y el negocio nuevo EMP-0002 (baseline por poca historia).

## Estado

- Todos los endpoints calculan sobre la BD (ya no hay mocks en el backend).
- BD real: las 27 tablas del DBML (`app/db/models.py`) y el seed de la demo (`app/db/seed_demo.py`). El seed cuadra
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
(componentes `forecast`, `credit_scoring` y `riesgo_atraso`). Código en `app/services/finanzas/` y `app/services/alertas/`; detalle de cada
regla en el docstring de su módulo y en `../contract.md`.

- **A fecha de corte:** todo se calcula al responder con lo registrado (`creado_en`) y ocurrido (`fecha_hora`) antes del
  fin del día de corte en Lima, sin lo anulado; lo fiado o pedido a crédito no mueve caja. Nada calculado se guarda;
  solo B escribe `alertas`, `forecast_ajustes` y `preferencias_alertas`.
- **Forecast:** LightGBM por cuantiles del equipo de datos (`FORECAST_MOTOR=lightgbm`, por defecto) para el flujo
  ordinario diario + pagos con fecha (deudas y cuotas, luz/sueldo programados, impuestos) + ajustes manuales; si el modelo
  no puede correr, baseline naive estacional (mismo día de la semana, últimas 4 semanas) con `meta.fallback_usado = true`
  y `meta.fallback_motivo` (ver "Modelos de ML"). Los fiados ponderados por su
  probabilidad de pago van a `cobros_esperados`, a la banda optimista y a "Lo que viene", **no** a la línea esperada:
  cobrar a tiempo es incierto y es la palanca "cobrar fiados" del simulador.
- **Alertas:** 7 reglas (faltante, pedido excesivo, retiro excesivo, obligación próxima, gasto inusual, fiado vencido por
  cliente y meta lograda; `caida_ventas` y `resumen_semanal` solo se muestran si vienen guardadas). `GET /alertas` **no
  escribe**: calcula las vigentes al momento (las guardadas con su monto y causas al día + las pendientes de guardar, con
  `persistida = false` y un `alerta_id` estable `ALR-PEND.…`). Se guardan en `POST /alertas/evaluar`, al confirmar un
  movimiento y al accionar una alerta pendiente; al reevaluar, la activa de la misma entidad se actualiza y la que ya no
  aplica se cierra (`ya_no_aplica`). Máx. 2 notificadas al día y horario silencioso: las que no se notifican se guardan con
  `enviada_en = null` (corre la demo fuera de 21:00–07:00 si quieres verlas como enviadas).
  **Limitación conocida (`pedido_excesivo`):** compara el pedido con lo que se vende de eso solo en los días que faltan
  hasta su vencimiento. Un pedido de rutina (p. ej. semanal) que vence en pocos días puede salir "excesivo" aunque sea el
  de siempre (falso positivo). No se cambia antes de la demo: la historia de Pedro (`PED-0012`, S/ 400 más) depende de
  esta regla; la mejora sería comparar con lo que el pedido cubre (su periodo habitual de reposición) o con los pedidos
  anteriores al mismo proveedor.
- **Sueldo fijo:** diario/semanal cuenta las veces que cae en el rango; mensual/quincenal se prorratea por día (un sueldo
  mensual de S/ 1 350 vale S/ 630 a mitad de mes) y, si el sueldo ya cayó en el periodo (p. ej. se cobra el día 1), cuenta
  completo (`max(prorrateo, sueldo ya vencido)`), así no hay `retiro_excesivo` falso. Lo usan alertas, score y `/resumen`.
- **Score de salud:** `GET /salud` calcula al vuelo y no escribe; `POST /salud/recalcular` guarda el del mes en curso. Trae
  además `score_crediticio` (modelo de credit scoring, aparte del score de 3 hábitos; ver "Modelos de ML").

### Modelos de ML (equipo de datos)

Artefactos en `../modelo/artifacts/` (`prediccion_ingreso_egreso/`: 6 `LGBMRegressor` ingreso/egreso × p10/p50/p90;
`credit_scoring/`: `LogisticRegression` + `StandardScaler`). **Van dentro de la imagen** (local y Render construyen lo
mismo): `backend/Dockerfile` usa como contexto la raíz del repo, copia `modelo/artifacts/{prediccion_ingreso_egreso,credit_scoring}`
a `/app/ml/artifacts` y fija `ML_ARTIFACTS_DIR`; el `.dockerignore` de la raíz es una lista blanca (backend + esos artefactos;
nunca `.env`). `docker-compose.yml` monta además `../modelo/artifacts` encima (solo lectura) para probar artefactos nuevos sin
reconstruir. Dependencias con versión exacta (`requirements.txt`): `lightgbm==4.7.0`, `scikit-learn==1.9.1`, `pandas==3.1.1`,
`numpy==2.5.4`, `scipy==1.18.1`, `joblib==1.6.0` (cargan los 8 pickles sin warnings) y `libgomp1` en la imagen (sin ella LightGBM
falla con `OSError libgomp.so.1`).

- **Carga:** perezosa y una sola vez por proceso (nunca al importar la app; `app/services/finanzas/modelo_ml.py`). Se valida
  contra `metadata.json` (nombres y orden de features, categorías de `rubro`, cuantiles, número de columnas). Un fallo (artefacto
  ausente, versión, `libgomp`) deja el modelo "no disponible" con el motivo y los motores usan su baseline.
  `GET /health` carga los modelos la primera vez (queda en caché) y reporta `forecast` y `credit_scoring` con estado real.
- **Memoria:** el proceso uvicorn pasa de ≈ 90 MB (app sin ML) a ≈ 240 MB RSS con LightGBM + scikit-learn + pandas cargados y
  tras servir forecast y salud (`VmRSS` de `/proc/1/status`); Whisper `base` (Render) se carga aparte y solo al transcribir:
  en el plan free (512 MB) queda poco margen para Whisper + ML a la vez.
- **Forecast** (`forecast_ml.py`): replica el `add_features` del notebook (lags 1/7/14, media y desviación ddof=1 de 7/14/30
  días con `shift(1).rolling`, calendario, perfil de la empresa con `rubro` categórico) sobre el flujo **ordinario** de la
  empresa; predice un paso y lo encadena (recursivo) hasta el horizonte; p10/p90 en lote; cuantiles ordenados; banda del saldo =
  suma de cuadrados de la dispersión diaria del lado malo/bueno, con piso en el error de 1 paso del modelo en esa empresa.
  Necesita 30 días completos de historia (si no: baseline con ese motivo). El día de corte no se usa como dato (puede estar a
  medias): se predice como cualquier otro y su p50 alimenta la recursión.
  `usa_fiado` / `usa_billetera_digital` = ≥ 1 registro en `cuaderno_fiado` / `billeteras_digitales` en los últimos 90 días
  (`definiciones_acordadas`, aplicadas al pie de la letra).
- **Credit scoring** (`app/services/salud/credito.py`): 16 features calculados en Python desde el ORM (las vistas del DBML son
  solo comentarios y tenían errores: ingreso mensual por transacción, 180 fijos de denominador, lo no vencido como atrasado,
  `CURRENT_DATE`, tipo de alerta que el backend no genera; las definiciones corregidas están en el docstring del módulo);
  `score = round(predict_proba(scaler.transform(X))[:, 1] * 100)`, Rojo 0–39 · Amarillo 40–69 · Verde 70–100. Bloque
  adicional `score_crediticio` en `GET /salud`; **no** reemplaza el score de 3 hábitos. Features sin datos se imputan con la
  media de entrenamiento y se listan. Es una estimación de un modelo entrenado con datos sintéticos, no una evaluación
  crediticia. Nunca usa `pago_tardio`, `deficit_14d`, `eventos` ni `clientes.perfil_pago`.
- **Riesgo de atraso:** no hay clasificador en `modelo/artifacts/`; se usa la tasa histórica de atraso del cliente.
- **`motor_recomendaciones` no se integra:** es un motor de reglas (`artifacts/motor_recomendaciones/config.json`); sus ideas
  útiles ya están implementadas en `services/alertas/reglas.py` como las reglas `gasto_inusual`, `fiado_vencido` y `meta_lograda`.

**Train/serve skew (la data de entrenamiento es sintética y distinta a `data/csv`; se integra igual por decisión del equipo):**

| Diferencia | Qué se hace |
|---|---|
| El modelo se entrenó con el egreso **total** de la caja (proveedores, impuestos y alquiler incluidos); el backend suma aparte los pagos con fecha | El modelo se aplica al flujo ordinario y los eventos conocidos van encima: sin doble conteo |
| En el entrenamiento los pagos grandes caían siempre los días 5 y 15: el egreso del modelo sube ≈ S/ 1 000 esos días | Solo en los modelos de egreso, `dom` 5→4 y 15→14 (mismo flag de quincena), para no inventar un pago |
| Un modelo de 1 paso: hace falta recursión para 30 días | Predicción recursiva con el p50; las desviaciones móviles futuras salen algo más chicas que las reales |
| Si en los últimos 30 días del flujo ordinario no hay ningún egreso grande (en el entrenamiento siempre había uno al mes, el día 5), el modelo lo "espera" y predice ≈ S/ 1 200 de egreso cada día (error a 1 día ≈ S/ 900) | Sin corrección en el backend; `data/csv` da a Pedro una compra grande al contado al mes (día 5) y su error a 1 día es S/ 82 |
| Escala y proporciones de las bodegas sintéticas (ingreso ≈ S/ 180/día, egreso ≈ 55 % del ingreso de ayer); `mes` solo vio junio–septiembre | Sin corrección (un reescalado por empresa se probó y era inestable): el sesgo se mide en `eval_forecast` y se informa |
| Los cuantiles del modelo son más angostos que el error real | Piso con el error de 1 paso de la propia empresa |
| `usa_billetera_digital` mira `billeteras_digitales` (el backend no escribe esa tabla: las ventas con `metodo_pago = billetera_digital` registradas por la app no la activan) | Regla acordada al pie de la letra; en `data/csv` actual coincide (1 292 filas = 1 292 ventas con billetera) |

### Backtest del forecast (B14)

```bash
docker compose run --rm backend python -m tests.eval_forecast              # BD de desarrollo, solo lectura
docker compose run --rm backend python -m tests.eval_forecast --test --json --horizonte 7
```

Compara los dos motores (baseline y LightGBM) sobre los mismos cortes (≥ 31 días de historia y `horizonte` días reales por
delante, usando solo lo que se sabía ese día): MAE / MAPE / sesgo / cobertura p10–p90 del saldo por horizonte (vs persistencia),
MAE del flujo ordinario de mañana (ingreso, egreso y neto, vs "igual que ayer") y precision / recall de `faltante_caja` contra
`saldo_diario.deficit_14d` (etiqueta solo para evaluar, nunca feature). `--empresa todas` resume las 29 empresas con historia.
Con `data/csv` (FECHA_DEMO = 14/11): en las 29 empresas el MAE del saldo a 7 días es, en promedio por empresa, 932 (baseline)
vs 912 (LightGBM; mejor en 19 de 29) y la cobertura de la banda 0.72 vs 0.59. En Pedro (EMP-0001, horizonte 14, 47 cortes) el
LightGBM le gana al baseline en todos los horizontes: MAE del saldo 232 vs 251 a 1 día, 442 vs 615 a 7 y 675 vs 823 a 14
(cobertura 0.72 vs 0.85), y MAE del flujo neto de mañana 95 vs 127 ("igual que ayer": 137). La historia de Pedro no tiene días
con déficit a 14 días (su 30/11 es futuro), así que ahí el recall del faltante no es medible.

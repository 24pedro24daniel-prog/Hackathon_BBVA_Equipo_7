# CajaClara — Backend

FastAPI + SQLAlchemy 2 + PostgreSQL 16. Plan: [PLAN_MVP.md](PLAN_MVP.md) · Contrato: [../contract.md](../contract.md) · Tablas: [../modelo_datos.dbml](../modelo_datos.dbml).
Todos los datos son sintéticos (Pedro, "Bodega Don Pedro", EMP-0001).

## Configuración (3 archivos)

| Archivo | Qué tiene | ¿Se versiona? |
|---|---|---|
| `parametros.env` | Parámetros no secretos: host/puerto/BD, `FECHA_DEMO=2026-11-14`, `TZ`, `LLM_*` (OpenRouter), `WHISPER_*`, `UMBRAL_CONFIANZA`, `R2_ACCOUNT_ID`, `R2_BUCKET`, `MEDIA_*` | Sí |
| `.env` | Solo credenciales: `POSTGRES_USER`, `POSTGRES_PASSWORD`, `API_KEY`, `OPENROUTER_API_KEY`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY` | **No** (`.gitignore`) |
| `example.env` | Plantilla de `.env` con valores vacíos | Sí |

```bash
cd backend
cp example.env .env        # y llena los valores (el archivo explica cómo generarlos)
```

`API_KEY` es la que el front manda en `X-API-Key` (ponla también en `frontend/.env` como `VITE_API_KEY`).
Sin `OPENROUTER_API_KEY` el backend funciona igual; el extractor y el asistente usarán su fallback.

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

## Levantar con Docker

```bash
docker compose up -d                                    # db (postgres:16.14) + backend en http://localhost:8000
docker compose run --rm backend python -m app.db.reset  # borra, crea las 25 tablas y siembra la demo de Pedro
curl http://localhost:8000/api/v1/health                # pública
curl -H "X-API-Key: <tu API_KEY>" http://localhost:8000/api/v1/empresas/EMP-0001/resumen
```

- Docs interactivas: <http://localhost:8000/api/v1/docs>.
- Postgres queda publicado en el host como **`localhost:5433`** (el 5432 puede estar ocupado por un PostgreSQL nativo);
  dentro de compose el backend usa `db:5432`. La primera vez se crea también la BD de pruebas `cajaclara_test`.
- `app/` y `tests/` están montados en el contenedor: tras cambiar código, `docker compose restart backend`.
  Si cambias `requirements.txt`: `docker compose build backend`.
- El modelo de Whisper (`small`) se descarga en la primera transcripción y queda en el volumen `whisper_models`.

## Tests

```bash
docker compose run --rm backend pytest -q               # dentro de docker (recomendado)
```

O fuera de docker (Python 3.12+, con la BD levantada en `localhost:5433`):

```bash
python -m venv .venv && .venv/Scripts/activate          # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
python -m app.db.reset                                  # BD principal
pytest -q
```

- Los tests usan **solo** `cajaclara_test`: la recrean y siembran una vez por sesión y cada test corre en una
  transacción que se revierte. Si Postgres no está accesible, los tests de BD se saltan con un aviso y el resto corre.
- El LLM y Whisper nunca se llaman de verdad en los tests (fixtures `llm_falso` y `whisper_falso` en `tests/conftest.py`).
- Convención: `tests/test_a_*.py` (Dev A: BD, seed, ingesta) y `tests/test_b_*.py` (Dev B: core, routers, motores).

## Estado (Fase 0)

Todos los endpoints del contrato responden con los JSON del mock de Pedro (`app/mock_contrato.py`) para que el front
pueda usar `VITE_USE_MOCK=false`. `/health` es real para la BD. Las interfaces congeladas entre devs están en
`app/services/ingesta/registrador.py` (A) y `app/services/finanzas/__init__.py`, `app/services/alertas/__init__.py` (B).

### Dev A (ingesta y conversación) — ya con BD real

`/webhooks/whatsapp`, `/ingesta/*`, `/movimientos`, `/impuestos`, `/asistente/mensajes`, `/salud` y `/metas` ya no
son stub. Los cálculos de B (saldo, forecast, chequeo, simulador, alertas) se llaman por su interfaz y siguen en mock
hasta que B los implemente (por eso `saldo_caja_negocio` sigue dando 2 340 tras registrar).

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

El seed (`app/db/seed_demo.py`) cuadra con la historia: caja S/ 2 340 al 14/11, pedido PED-0012 de S/ 2 400 a
Distribuidora Andina que vence el 30/11, fiados pendientes S/ 310, retiros +S/ 700 sobre lo usual, y la proyección de
referencia documentada en el módulo da −S/ 650 el 30/11.

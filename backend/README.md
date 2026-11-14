# CajaClara — Backend

FastAPI + SQLAlchemy 2 + PostgreSQL 16. Plan: [PLAN_MVP.md](PLAN_MVP.md) · Contrato: [../contract.md](../contract.md) · Tablas: [../modelo_datos.dbml](../modelo_datos.dbml).
Todos los datos son sintéticos (Pedro, "Bodega Don Pedro", EMP-0001).

## Configuración (3 archivos)

| Archivo | Qué tiene | ¿Se versiona? |
|---|---|---|
| `parametros.env` | Parámetros no secretos: host/puerto/BD, `FECHA_DEMO=2026-11-14`, `TZ`, `LLM_*` (OpenRouter), `WHISPER_*`, `UMBRAL_CONFIANZA` | Sí |
| `.env` | Solo credenciales: `POSTGRES_USER`, `POSTGRES_PASSWORD`, `API_KEY`, `OPENROUTER_API_KEY` | **No** (`.gitignore`) |
| `example.env` | Plantilla de `.env` con valores vacíos | Sí |

```bash
cd backend
cp example.env .env        # y llena los valores (el archivo explica cómo generarlos)
```

`API_KEY` es la que el front manda en `X-API-Key` (ponla también en `frontend/.env` como `VITE_API_KEY`).
Sin `OPENROUTER_API_KEY` el backend funciona igual; el extractor y el asistente usarán su fallback.

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
- Voz: `media_url` se lee solo dentro de `MEDIA_DIR` (`file://data/...`, `demo://...`); si no hay archivo y el
  cliente manda `texto` (notas de voz demo del front), se usa ese texto como transcripción.
- Cuaderno de fiados: sin modelo de visión; fixtures por foto (`cuaderno_01..03`) con `fallback_usado = true`.
- Evaluación del extractor: `docker compose run --rm backend python -m tests.eval_extractor` (offline, reglas);
  `--llm` agrega la ruta LLM (1 llamada a OpenRouter por frase).

El seed (`app/db/seed_demo.py`) cuadra con la historia: caja S/ 2 340 al 14/11, pedido PED-0012 de S/ 2 400 a
Distribuidora Andina que vence el 30/11, fiados pendientes S/ 310, retiros +S/ 700 sobre lo usual, y la proyección de
referencia documentada en el módulo da −S/ 650 el 30/11.

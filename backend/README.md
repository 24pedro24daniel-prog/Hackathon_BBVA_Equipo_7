# CajaClara — Backend (FastAPI)

FastAPI + SQLAlchemy 2 + PostgreSQL 16. Plan y reparto A/B: [PLAN_MVP.md](PLAN_MVP.md) · Contrato: [../contract.md](../contract.md) · Tablas: [../modelo_datos.dbml](../modelo_datos.dbml).
Todos los datos son sintéticos (Pedro, "Bodega Don Pedro", EMP-0001).

## Configuración (3 archivos)

| Archivo | Qué tiene | ¿Se versiona? |
|---|---|---|
| `parametros.env` | Parámetros no secretos: host/puerto/BD, `FECHA_DEMO=2026-11-14`, `TZ`, `LLM_*` (OpenRouter), `WHISPER_*`, `UMBRAL_CONFIANZA` | Sí |
| `.env` | Solo credenciales: `POSTGRES_USER`, `POSTGRES_PASSWORD`, `API_KEY`, `OPENROUTER_API_KEY` | **No** (`.gitignore`) |
| `example.env` | Plantilla de `.env` con valores vacíos | Sí |

```bash
cd backend
cp example.env .env        # Windows: copy example.env .env — y llena los valores (el archivo explica cómo generarlos)
```

- `API_KEY` es obligatoria: todas las rutas salvo `/health` exigen `X-API-Key`. Ponla también en `frontend/.env` como `VITE_API_KEY`.
- Sin `OPENROUTER_API_KEY` el backend funciona igual; el extractor y el asistente usarán su fallback.

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

## Tests

```bash
docker compose run --rm backend pytest -q               # dentro de docker
pytest -q                                               # o con el venv
```

- Los tests usan **solo** `cajaclara_test`: la recrean y siembran una vez por sesión y cada test corre en una
  transacción que se revierte. Si Postgres no está accesible, los tests de BD se saltan con un aviso y el resto corre.
- La API key de los tests es fija (`tests/conftest.py`); nunca se usan las credenciales de `.env`.
- Convención: `tests/test_a_*.py` (Dev A: BD, seed, ingesta) y `tests/test_b_*.py` (Dev B: core, routers, motores).

## Estado (Fase 0)

- Todos los endpoints responden con el JSON del mock de Pedro (`app/mocks/`) para que el front pueda usar
  `VITE_USE_MOCK=false`. Los routers `webhooks`, `ingesta`, `impuestos`, `movimientos`, `asistente`, `salud` son
  *stubs* de Dev A (`app/mocks/stubs_a.py`). `app/mocks/` se borra al terminar el MVP.
- BD real: las 25 tablas del DBML (`app/db/models.py`) y el seed de la demo (`app/db/seed_demo.py`). El seed cuadra
  con la historia: caja S/ 2 340 al 14/11, pedido PED-0012 de S/ 2 400 a Distribuidora Andina que vence el 30/11,
  fiados pendientes S/ 310 y retiros +S/ 700 sobre lo usual.
- `/health` consulta la BD de verdad.
- Interfaces congeladas entre devs: `app/services/finanzas/__init__.py` y `app/services/alertas/__init__.py` (B);
  `app/services/ingesta/registrador.py` (A, llega con las tareas de A).

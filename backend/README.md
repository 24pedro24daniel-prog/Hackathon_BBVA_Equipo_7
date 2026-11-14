# CajaClara — Backend (FastAPI)

Plan y reparto A/B: [PLAN_MVP.md](PLAN_MVP.md) · Contrato: [../contract.md](../contract.md)

## Puesta en marcha

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows   (Mac/Linux: source .venv/bin/activate)
pip install -r requirements.txt
copy .env.example .env          # Mac/Linux: cp .env.example .env
uvicorn app.main:app --port 8000 --reload
```

- Docs interactivas: http://localhost:8000/docs
- Health: http://localhost:8000/api/v1/health
- Front contra este backend: en `frontend/.env` poner `VITE_USE_MOCK=false` (y `VITE_API_KEY` = `API_KEY` del `.env` del backend).

## Tests

```bash
pytest tests/test_b_smoke.py -v
```

## Estado

**Fase 0 (B):** todos los endpoints responden con el JSON del mock (`app/mocks/`).
Los routers `webhooks`, `ingesta`, `impuestos`, `movimientos`, `asistente`, `salud` son *stubs* de Dev A.
`app/mocks/` se borra al terminar el MVP.

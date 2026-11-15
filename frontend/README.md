# TuCaserito — Frontend

React 19 + Vite + react-router. Mobile-first (360 px). Implementa el mockup `mockup/CajaClara — Mockup MVP.pdf` y consume la API de `contract.md`.

## Correr

```bash
cd frontend
cp .env.example .env      # opcional; por defecto usa mocks
npm install
npm run dev               # http://localhost:5173
```

## Pantallas

| Ruta | Pantalla (mockup) | Endpoints |
|---|---|---|
| `/` | ¿Cómo va mi caja? (p. 5) · Día 3 (p. 10) | `GET /resumen`, `GET /forecast`, `GET /alertas` |
| `/30-dias` | Así se mueve tu caja (p. 6) | `GET /forecast` |
| `/simulador` | ¿Qué puedo hacer? (p. 7) | `POST /simular`, `GET /fiados` |
| `/cuentas` | Lo que te deben y lo que debes (p. 8) | `GET /fiados`, `POST /fiados/{id}/recordatorio`, `GET /pedidos` |
| `/progreso` | Tu negocio, más ordenado (p. 9) | `GET /salud` |
| `/chat` | Chat simulado: registro, pedido, alertas, fiados (p. 1–4) | `/ingesta/*`, `/pedidos/chequeo`, `/asistente/mensajes`, `/alertas` |

El chip **Demo** (Inicio) cambia entre Pedro con 3 meses de datos y Pedro en su día 3, y simula el asistente caído (modo básico). Solo afecta a los mocks.

## Conectar el backend

Todo pasa por `src/api/` — las pantallas nunca importan los mocks.

1. Levanta FastAPI en `http://localhost:8000` (base `/api/v1`).
2. En `frontend/.env`:
   ```
   VITE_USE_MOCK=false
   VITE_PROXY_TARGET=http://localhost:8000
   VITE_API_KEY=<clave de la demo>   # se manda como X-API-Key; nunca la subas al repo
   ```
3. `npm run dev`. Vite proxea `/api` al backend (sin CORS en desarrollo).

`src/api/client.js` agrega `X-API-Key`, `Idempotency-Key` en los POST que crean registros, y convierte el formato de error del contrato en `ApiError { status, codigo, mensaje, detalles, requestId }`.

## Estructura

```
src/
  api/          client.js (fetch + mock switch), index.js (una función por endpoint), useApi.js
  mocks/        data.js (JSON del contrato con datos de Pedro), handlers.js (rutas + simulador determinístico)
  components/   ui/ (Card, Button, Badge, TraceInfo, …), layout/ (AppLayout + nav, DemoMenu)
  lib/          format.js (S/ 2 340, 30/11), demo.js, useDemo.js
  pages/        Inicio, Forecast, Simulador, Cuentas, Progreso, Chat
```

## Extensiones propuestas al contrato

El mockup necesita algunos campos que `contract.md` no define. Los mocks los incluyen (marcados `// EXT` en `src/mocks/data.js`); el backend debería agregarlos o el front los deriva:

| Endpoint | Campo | Para qué |
|---|---|---|
| `GET /resumen` | `dias_con_datos`, `dias_requeridos_forecast` | Estado "día 3" del Inicio |
| `GET /resumen` | `indicadores.pagos_pendientes.detalle` | "Andina + RUS" |
| `GET /forecast` | `disponible`, `dias_con_datos`, `dias_requeridos` | Forecast sin historial suficiente |
| `GET /forecast` | `proximos_eventos[] {fecha, concepto, monto, tipo}` | Lista "Lo que viene" |
| `GET /forecast`, `GET /fiados`, `POST /simular` | `fundamento`, `limites`, `confianza` | "¿De dónde sale este número?" |
| `GET /fiados` | `items[].detalle` | "panes, leche" |
| `GET /pedidos` | `impuestos.nombre` | "RUS de noviembre" |
| `GET /pedidos` | `impuestos.impuesto_id` | Identifica el impuesto al eliminarlo |
| `GET /alertas` | `dias_para_evento`, `titulo_corto`, `resumen_causas` | Tarjeta de alerta del Inicio y del chat |
| `GET /salud` | `etapas[]`, `subindicadores[].destacado`, `metas_activas[]` | Pantalla Progreso |
| `POST /ingesta/interpretar` | `opciones_aclaracion[] {valor, texto}` | Botones de respuesta rápida (30/11 · 30/12) |
| `POST /ingesta/cuaderno` | `fiados_propuestos[].alternativas_monto` | "¿son S/ 95 o S/ 35?" |
| `POST /asistente/mensajes` | `tabla[]`, `ejemplo_prestamo_informal`, `respuesta_post`, `acciones[]` | Modo básico, costo del préstamo informal, botones |

Todos los datos son sintéticos.

### Eliminar cobros y pagos en la demo

En `/cuentas`, cada fiado, deuda de proveedor e impuesto tiene un botón **Eliminar**. La demo implementa
`POST /empresas/{empresa_id}/cuentas/anular` con `{ tipo: "fiado" | "pedido" | "impuesto", id }`.
Conserva el registro con `anulada: true`, lo excluye de los pendientes y actualiza sus totales sin mover la caja
ni registrar un cobro o pago. Las anulaciones se mantienen al navegar durante la sesión y se separan por
escenario; al recargar se reinician los mocks. Este endpoint es una extensión de demo pendiente de implementar
en el backend real.

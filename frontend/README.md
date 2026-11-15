# TuCaserito — Frontend

React 19 + Vite + react-router. Mobile-first (360 px). Implementa el mockup `mockup/CajaClara — Mockup MVP.pdf` y consume la API de `contract.md`.
Se publica en Vercel (`https://www.cclara.site`; `cclara.site` redirige ahí); el backend vive en Render (`https://cajaclara-backend-ulah.onrender.com`, API en `https://cajaclara-backend-ulah.onrender.com/api/v1`).

## Correr

```bash
cd frontend
cp .env.example .env      # el front no lleva claves: se entra con el login de las demos
npm ci                    # respeta package-lock.json
npm run dev               # http://localhost:5173
npm run lint && npm run build
```

## Pantallas

| Ruta | Pantalla (mockup) | Endpoints |
|---|---|---|
| `/` | Landing pública: qué es TuCaserito y "Probar la demo" | `GET /health` (solo para despertar el backend) |
| `/ingresar` | Login de las demos. Con sesión abierta lleva a `/app` | `POST /auth/login` |
| `/app` | ¿Cómo va mi caja? (p. 5) · Día 3 (p. 10) | `GET /resumen`, `GET /forecast`, `GET /alertas` |
| `/app/30-dias` | Así se mueve tu caja (p. 6) | `GET /forecast` |
| `/app/simulador` | ¿Qué puedo hacer? (p. 7). `?pedido_id=` elige el pedido (viene del payload de la alerta) | `GET /forecast`, `GET /pedidos`, `GET /fiados`, `POST /pedidos/chequeo`, `POST /simular` |
| `/app/cuentas` | Lo que te deben y lo que debes (p. 8). `?recordar=FIA-…` o `?cliente=CLI-…` deja listo el mensaje de recordatorio | `GET /fiados`, `GET /pedidos`, `POST /fiados/{id}/recordatorio`, `POST /cuentas/anular` |
| `/app/progreso` | Tu negocio, más ordenado (p. 9). Aquí se crean las metas | `GET /salud`, `POST /metas` |
| `/app/chat` | Chat: registro, pedido, alertas, fiados (p. 1–4); voz y foto reales | `POST /media/subidas` + `PUT` a R2, `POST /chat/mensajes`, `POST /ingesta/{confirmar,cuaderno}`, `POST /pedidos/chequeo`, `POST /simular`, `GET /alertas`, `GET /fiados`, `GET /pedidos` |
| `/app/movimientos` | Tus movimientos (ruta oculta, desde Inicio). `?id=MOV-…` abre uno; `?tipo=retiro_personal` filtra | `GET /movimientos` |

Todo `/app/*` exige sesión: sin sesión lleva a `/ingresar` (y, al entrar, de vuelta a la pantalla que se pidió). Las pantallas de la app
se cargan aparte (`React.lazy`), así que quien solo abre la landing o el login no descarga su código.

### Login de las demos (`AUTH_CONTRATO`)

- Solo hay 3 cuentas de demo (no hay registro). Cada una abre una empresa: demo 1 = Bodega Don Pedro (3 meses, no le alcanza el 30/11),
  demo 2 = Bodega SurAndina (EMP-0030, bodega sana: sí le alcanza), demo 3 = Bodega Nueva Esperanza (día 3). Las credenciales **no** se muestran en la página:
  se comparten aparte.
- `POST /auth/login` devuelve `{ token, expira, usuario, empresa_id, negocio: { nombre } }`. El front lo guarda en `sessionStorage`
  (`tucaserito-sesion`, con try/catch; si el storage está bloqueado, dura mientras la página siga abierta) y manda
  `Authorization: Bearer <token>` en cada llamada (`src/api/client.js`). La empresa sale de `empresa_id`: no hay menú de empresas.
- Un 401 en cualquier llamada borra la sesión y vuelve a `/ingresar` con "Tu sesión venció". **Cerrar sesión** (menú **Demo** de Inicio
  y, en tablet/escritorio, la barra lateral) borra el token para entrar con otra demo. El nombre del negocio de la sesión se ve en
  Inicio y en la barra lateral.
- El login tiene usuario y contraseña con `autocomplete="username"`/`"current-password"`, botón para mostrar/ocultar la contraseña,
  botón deshabilitado mientras espera, aviso "Despertando el servidor…" si tarda más de 4 s (Render free duerme el backend: el primer
  login puede tardar ~30–50 s; la espera se corta a los 90 s) y mensajes para 401, 429 (cuenta regresiva con `Retry-After`), sin
  conexión y errores del servidor. La landing y el login piden `GET /health` al abrirse para ir despertando el backend.
- Para leer `Retry-After` desde otro origen, el backend debe exponerlo en CORS (`expose_headers=["Retry-After"]`); si no llega, el login
  dice "Espera un momento" sin cuenta regresiva.

### Audio y fotos en el chat

- **Nota de voz** (`useGrabadora.js` + `Composer.jsx`): mantener presionado el micrófono graba y al soltar envía; un toque corto
  (o Enter/Espacio con el teclado) empieza a grabar y otro toque envía; la X cancela. `getUserMedia` + `MediaRecorder` con el
  primer formato que el navegador soporte y el backend acepte (`audio/webm;codecs=opus` en Chrome/Edge, `audio/ogg` en Firefox,
  `audio/mp4` en Safari); se manda el tipo base (`audio/webm`). Máximo 60 s (se envía sola) y 10 MB; mínimo 1 s. Estados:
  pidiendo permiso, grabando (con tiempo), "Subiendo tu audio…", "Escuchando tu audio…" (Whisper + extractor). Permiso denegado,
  sin micrófono, micrófono ocupado o navegador sin soporte muestran un aviso claro con la alternativa de escribir o usar una
  **nota de prueba**. La nota grabada se puede escuchar en su burbuja.
- **Foto del cuaderno**: `<input type="file" accept="image/*" capture="environment">` (cámara en el móvil, archivo en escritorio).
  Se achica en el navegador (lado mayor 1600 px, JPEG ~0.82, respeta la orientación EXIF) y se muestra una vista previa antes de
  enviar. Luego `/ingesta/cuaderno` y la tarjeta de fiados de siempre.
- **Subida** (`src/api/subidas.js`): `POST /media/subidas` (Bearer) → `PUT` directo a la URL prefirmada de R2 con el `Content-Type`
  exacto de `headers_requeridos` (sin token) → `media_url` `r2://…` en `/chat/mensajes` (canal `voz`, `texto: null`) o en
  `/ingesta/cuaderno`. Si el `PUT` responde 403 (URL vencida) se pide otra URL una vez. Errores con texto para Pedro y botón
  "Intentar otra vez" (vuelve a subir el mismo archivo): 503 (R2 o Whisper no disponibles), 400/413/415 (tipo o tamaño), 429 (con
  `Retry-After`), sin conexión.
- **Guiones de demo** (`?demo=registro|fiados…`) siguen usando las notas y la foto de prueba (`demo://`). Con `VITE_USE_MOCK=true`
  la subida se simula y un audio grabado se "transcribe" siempre como "vendí dos cervezas".
- **CORS del bucket R2**: el `PUT` sale del navegador, así que el bucket debe permitir los orígenes del front. En el panel de
  Cloudflare: **R2 Object Storage → bucket → Settings → CORS Policy → Add CORS policy / Edit** y agrega (sin borrar reglas
  existentes) esta regla al arreglo:

  ```json
  {
    "AllowedOrigins": ["http://localhost:5173", "https://cclara.site", "https://www.cclara.site"],
    "AllowedMethods": ["PUT", "GET"],
    "AllowedHeaders": ["Content-Type"],
    "ExposeHeaders": ["ETag"],
    "MaxAgeSeconds": 3600
  }
  ```

  Para comprobarlo, pide una `upload_url` con `POST /media/subidas` y lanza un preflight:
  `curl -i -X OPTIONS "<upload_url>" -H "Origin: https://cclara.site" -H "Access-Control-Request-Method: PUT" -H "Access-Control-Request-Headers: content-type"`
  debe responder 200/204 con `Access-Control-Allow-Origin`. Sin esa regla responde 403 y el navegador bloquea la subida (el chat
  dice "No pude subir el archivo…").

### Alertas

`src/lib/alertas.js` decide a dónde lleva el botón de una alerta (Inicio y Chat) según `accion.tipo` y `accion.payload` del backend:
`abrir_simulador` → `/app/simulador?pedido_id=…`, `ver_retiros` → `/app/movimientos?tipo=retiro_personal`, `ver_cuentas` → `/app/cuentas`,
`recordar_cliente` → `/app/cuentas?recordar=…`, `ver_progreso` → `/app/progreso`. Si la acción o el `tipo` de la alerta son nuevos y no se
conocen, se usa un ícono genérico y, si no hay a dónde llevar, no se muestra botón (nunca se rompe la pantalla).

El chip **Demo** (Inicio) muestra u oculta los detalles técnicos (modelo, versión) y tiene "Cerrar sesión" (para cambiar de demo).
Con `VITE_USE_MOCK=true` además simula el asistente caído.

## Conectar el backend

El front llama al backend real por defecto. Todo pasa por `src/api/` — las pantallas nunca importan los mocks.

1. Backend (en `backend/`): `docker compose up -d` y cargar los datos (ver `backend/README.md`). El backend necesita `AUTH_SECRET` y
   las cuentas de demo (ver `AUTH_CONTRATO`).
2. `npm run dev` y entra por `http://localhost:5173/ingresar` con una cuenta de demo. Vite proxea `/api` a `VITE_PROXY_TARGET`
   (por defecto `http://localhost:8000`, sin CORS en desarrollo).

El front **no lleva ninguna clave** (antes una API key quedaba dentro del bundle publicado y cualquiera podía sacarla). La clave de
administración del backend sigue existiendo solo para el bot y la administración; nunca se pone en el front.

Sin backend: `VITE_USE_MOCK=true` usa los mocks de `src/mocks` (respaldo para la demo). El login también funciona: `src/mocks/auth.js`
imita el contrato (demo1/demo2/demo3 → escenarios `pedro`/`sano`/`nuevo`, 401, 429 con `Retry-After` tras 5 fallos, 403 si se pide
otra empresa) y guarda solo el SHA-256 de las credenciales. Los mocks se cargan con `import()` solo en ese modo: con
`VITE_USE_MOCK=false` no entran al build. Siguen la forma de `contract.md` (estados `pendiente`/`por_vencer`/`vencido`,
`retiro_personal`, `comparacion_pares: null`, los tres hábitos del puntaje, `notas`/`ventana_hasta` del simulador…).

`src/api/client.js` agrega `Authorization: Bearer` (token de la sesión), `Idempotency-Key` en los POST que crean registros, y convierte
el formato de error del contrato en `ApiError { status, codigo, mensaje, detalles, requestId, retryAfter }`. Las pantallas muestran
`error.message` (el texto del backend, escrito para el usuario).

## Variables de entorno

| Variable | Para qué |
|---|---|
| `VITE_USE_MOCK` | `true` = mocks (con login simulado); `false` = backend real |
| `VITE_API_BASE` | Base de la API. `/api/v1` en desarrollo (proxy); URL absoluta en producción |
| `VITE_PROXY_TARGET` | Destino del proxy de `npm run dev` |
| `VITE_EMPRESA_ID` | Solo modo mock: empresa de la cuenta demo1 (`EMP-0001`). Con backend real la empresa sale del token |

Toda variable `VITE_*` queda dentro del bundle publicado: nunca pongas secretos en ellas. El saludo de Inicio dice "¡Hola!" y, debajo,
el nombre del negocio de la sesión; si el backend manda `negocio.duenio` (opcional), el saludo lo usa ("¡Hola, Pedro!").

## Despliegue (Vercel)

Publicado con el CLI de Vercel (sin integración con Git: un push **no** despliega). `frontend/vercel.json` define el build, el
rewrite de SPA y los headers de seguridad; el backend sigue en Render.

| | |
|---|---|
| Proyecto | `tucaserito` (equipo `sebastian-salirrosas-projects`), framework Vite, `npm ci` → `npm run build` → `dist`, Node 24.x |
| Producción | `https://www.cclara.site` (principal). `https://cclara.site` redirige (308) a `www`. `https://tucaserito.vercel.app` sirve lo mismo, pero el backend no le da CORS: el login solo funciona desde `cclara.site`/`www.cclara.site` |
| Variables (Production y Preview) | `VITE_API_BASE=https://cajaclara-backend-ulah.onrender.com/api/v1`, `VITE_USE_MOCK=false`. Ninguna clave |
| DNS (en el proveedor del dominio, nameservers `dns-parking.com`) | `A  @  76.76.21.21` y `CNAME  www  cname.vercel-dns.com`. Verificados, con certificado de Let's Encrypt |

Las variables `VITE_*` se leen al construir: si cambian, hay que redesplegar. Para redesplegar, desde `frontend/` (con `vercel login`
hecho; la primera vez en otra máquina, `vercel link --project tucaserito`):

```bash
vercel deploy --prod      # sube frontend/ (sin .env ni node_modules: ver .vercelignore), construye en Vercel y publica
vercel deploy             # preview (URL protegida con Vercel Authentication; no tiene CORS en el backend)
```

Revisa después: `/`, `/ingresar` y `/app/30-dias` (recarga directa) devuelven el `index.html`; un `/assets/x.js` que no existe da 404;
`curl -I https://www.cclara.site` trae los headers de seguridad; el login con una demo entra y la consola no muestra bloqueos de CSP.

Qué hace `vercel.json`:

- **Rewrite de SPA**: todo lo que no exista como archivo va a `/index.html` (el `BrowserRouter` necesita que `/app/cuentas`,
  `/ingresar`… devuelvan el `index.html`). Vercel sirve primero los archivos reales; `/assets/*` queda fuera del rewrite para que un
  chunk que no existe dé 404 y no HTML. Los `/assets/*` (con hash en el nombre) se cachean un año.
- **Headers de seguridad**: `Content-Security-Policy` (abajo), `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
  `Referrer-Policy: strict-origin-when-cross-origin`, `Permissions-Policy` (micrófono y cámara solo para el propio sitio; el resto
  apagado), `Strict-Transport-Security` (2 años, con subdominios) y `Cross-Origin-Opener-Policy: same-origin`.
- **CSP**, ajustada a lo que la app usa:
  - `script-src 'self'`: solo los bundles de Vite (sin scripts inline ni `eval`).
  - `style-src 'self' https://fonts.googleapis.com` y `font-src 'self' https://fonts.gstatic.com`: la hoja de Vite y Libre Franklin de
    Google Fonts. Los `style={{…}}` de React se aplican por CSSOM y no necesitan `'unsafe-inline'`.
  - `connect-src 'self' https://cajaclara-backend-ulah.onrender.com https://*.r2.cloudflarestorage.com`: la API y el `PUT` de las subidas de
    voz y fotos a la URL prefirmada de Cloudflare R2 (`POST /media/subidas`). **El host del backend debe coincidir con
    `VITE_API_BASE`** (sin `/api/v1`): si el backend cambia de URL, actualiza ambos o el navegador bloqueará todas las llamadas.
  - `img-src 'self' data: blob:` y `media-src 'self' blob:`: vistas previas de fotos y notas de voz grabadas en el navegador
    (`getUserMedia` + `MediaRecorder`, permitido por `Permissions-Policy: microphone=(self), camera=(self)`).
  - `frame-ancestors 'none'`, `frame-src 'none'`, `object-src 'none'`, `worker-src 'none'`, `base-uri 'self'`, `form-action 'self'`,
    `upgrade-insecure-requests`.
- **CORS** (lado backend): el backend debe aceptar `https://cclara.site` y `https://www.cclara.site` (sin barra final) con los headers
  `Authorization`, `Content-Type` e `Idempotency-Key`, y exponer `Retry-After`. Un deploy de *preview* de Vercel (`*.vercel.app`) no
  está en esa lista: para probarlo contra el backend real hay que agregar su origen en el backend.

## Estructura

```
src/
  api/          client.js (fetch + Bearer + mock switch), index.js (una función por endpoint), subidas.js (R2), useApi.js
  mocks/        data.js (JSON del contrato con datos de Pedro), handlers.js (rutas + simulador determinístico), auth.js (login simulado)
  components/   ui/ (Card, Button, Badge, TraceInfo, …), layout/ (AppLayout + nav, DemoMenu, Logo), auth/ (RequireAuth)
  lib/          format.js (S/ 2 340 con espacio, como el backend; 30/11), alertas.js (destino de cada alerta),
                sesion.js + useSesion.js (token en sessionStorage), demo.js + useDemo.js (detalles técnicos, fallback del LLM), useTitulo.js
  pages/        Landing (+ marca.css, DotFan, PhoneDemo, SiteBar), Ingresar, Inicio, Forecast, Simulador, Cuentas, Progreso, Chat, Movimientos
```

La landing y el login comparten `pages/Landing/marca.css`: barra oscura, panel navy con la curva Electric y el abanico de puntos
(`DotFan`: las trayectorias posibles del saldo a 30 días, dibujadas con puntos) y el botón píldora. El teléfono de la landing
(`PhoneDemo`) es HTML/CSS con las mismas cifras ficticias de la demo de Pedro.

## Campos que el front usa fuera del contrato base

`contract.md` ya incluye como "campos extra" la mayoría de lo que el mockup necesitaba (`dias_con_datos`, `dias_requeridos_forecast`,
`pagos_pendientes.detalle`, `proximos_eventos`, `fundamento`/`limites`/`confianza`, `disponible`, `impuestos.nombre`/`impuesto_id`,
`titulo_corto`/`resumen_causas`/`dias_para_evento`, `etapas`, `metas_activas`, `notas`/`ventana_hasta` del simulador, `cuentas/anular`, etc.).
Lo que el front lee y el contrato todavía no formaliza (o es opcional):

| Endpoint | Campo | Para qué |
|---|---|---|
| `POST /ingesta/interpretar` | `opciones_aclaracion[] {valor, texto}` | Botones de respuesta rápida (30/11 · 30/12) |
| `POST /ingesta/cuaderno` | `fiados_propuestos[].alternativas_monto` | "¿son S/ 95 o S/ 35?" |
| `POST /asistente/mensajes` | `acciones[]`, `tabla[]`, `ejemplo_prestamo_informal`, `respuesta_post` | Botones, modo básico, costo del préstamo informal |
| `GET /fiados` | `items[].detalle` | "panes, leche" |
| `POST /auth/login` | `negocio.duenio` (opcional) | "¡Hola, Pedro!" en Inicio; sin él, "¡Hola!" y el nombre del negocio |

Todos los datos son sintéticos.

### Eliminar cobros y pagos

En `/app/cuentas`, cada fiado, deuda de proveedor e impuesto tiene un botón **Eliminar** que llama a
`POST /empresas/{empresa_id}/cuentas/anular` con `{ tipo: "fiado" | "pedido" | "impuesto", id }` (contract.md §4.4.1; el backend ya lo implementa).
No borra nada: marca el registro como anulado y lo saca de pendientes, forecast, simulador y alertas. Si falla, se muestra el mensaje real del
backend (`404 NO_ENCONTRADO`, `409 CONFLICTO` si el impuesto ya tiene un pago anotado, etc.). Los mocks lo imitan durante la sesión.

### Metas

En `/app/progreso`, "Crear una meta" lista las plantillas que aún no están activas y llama a `POST /empresas/{empresa_id}/metas`
(`plantilla`, `regla`, `recordatorio`). Las plantillas por porcentaje usan valores fijos (apartar para el pedido 10 %, colchón y
reservar impuestos 5 %); solo el sueldo fijo pide el monto semanal y, con `monto_fijo`, el backend crea además el sueldo programado
(cambia el forecast). El asistente del chat responde "elige una en «Tu progreso»" (texto del backend) y ahora Progreso sí permite crearla.

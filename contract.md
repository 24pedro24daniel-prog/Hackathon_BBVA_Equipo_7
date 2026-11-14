# CajaClara — Contratos de API (v1)

> Contratos para que cada parte del equipo trabaje en paralelo (backend, ML, GenAI, front y bot).
> Implementación sugerida: FastAPI + pydantic. Todos los datos son sintéticos.

---

## 0. Convenciones generales

| Tema | Regla |
|---|---|
| Base URL | `/api/v1` |
| Formato | JSON, UTF-8 |
| Autenticación (demo) | Header `X-API-Key: <clave>` leída desde `.env`. Nunca en el código ni en el repo |
| IDs | Strings con prefijo: `EMP-0001`, `MOV-000123`, `FIA-0045`, `PED-0012`, `ALR-0007`, `BOR-…` (borrador) |
| Dinero | Número decimal en soles con 2 decimales (`2340.00`). Campo `moneda` = `"PEN"` por defecto |
| Fechas | ISO 8601. Fecha: `2026-11-30`. Fecha-hora: `2026-11-14T10:42:00-05:00` (zona America/Lima) |
| Paginación | `?limit=50&cursor=<token>` → respuesta con `next_cursor` (null si no hay más) |
| Idempotencia | Los `POST` que crean registros aceptan header `Idempotency-Key` (evita duplicar si WhatsApp reenvía el mensaje) |
| Trazabilidad | Toda respuesta con salida de un modelo incluye el bloque `meta` (ver abajo) |
| Explicabilidad | Toda recomendación incluye `fundamento`, `limites` y `confianza` |

### Bloque `meta` (en respuestas de modelos)

```json
"meta": {
  "request_id": "req_8f3a1c",
  "generado_en": "2026-11-14T10:42:05-05:00",
  "modelo": "forecast-lgbm-quantile",
  "modelo_version": "0.3.1",
  "prompt_version": null,
  "fallback_usado": false,
  "latencia_ms": 184
}
```

### Formato de error

```json
{
  "error": {
    "codigo": "VALIDACION",
    "mensaje": "El campo 'monto' debe ser mayor que 0.",
    "detalles": [{ "campo": "monto", "problema": "must be > 0" }],
    "request_id": "req_8f3a1c"
  }
}
```

| HTTP | `codigo` | Cuándo |
|---|---|---|
| 400 | `VALIDACION` | Payload inválido |
| 401 | `NO_AUTORIZADO` | Falta o es inválida la API key |
| 404 | `NO_ENCONTRADO` | Empresa, borrador o registro inexistente |
| 409 | `CONFLICTO` | Borrador ya confirmado / idempotency key repetida con otro payload |
| 422 | `NO_INTERPRETABLE` | El LLM/OCR no pudo extraer un movimiento |
| 503 | `SERVICIO_NO_DISPONIBLE` | LLM, Whisper o R2 (almacenamiento de media) caídos o sin configurar (se responde con fallback cuando existe) |

### Enums compartidos

```text
tipo_movimiento : venta | cobro_fiado | prestamo_recibido | otro_ingreso                                        (ingresos)
                | compra | gasto_negocio | retiro_personal | pago_proveedor | pago_prestamo | pago_impuesto   (egresos)
metodo_pago     : efectivo | billetera_digital | transferencia | tarjeta | credito   (credito = fiado o pedido a crédito: no mueve caja)
tipo_deuda      : proveedor | prestamo_informal | familiar | entidad_financiera
canal           : voz | texto | foto | billetera_api | manual
estado_cuenta   : pendiente | por_vencer | vencido | pagado
nivel_riesgo    : bajo | medio | alto
estado_caja     : te_alcanza | justo | no_te_alcanza
tipo_alerta     : faltante_caja | pedido_excesivo | retiro_excesivo | obligacion_proxima | gasto_inusual | caida_ventas | fiado_vencido | meta_lograda | resumen_semanal
```

---

## 1. F1 — Ingesta (registro multicanal)

Flujo: **interpretar → (aclarar) → confirmar → guardar**. Nada se guarda sin confirmación, salvo `billetera_api`.

### 1.0 `POST /media/subidas` (subir audio o foto a Cloudflare R2)
Pide una **URL prefirmada** para subir el archivo directo a R2 (el archivo no pasa por el backend). Requiere `X-API-Key`.

Flujo de 3 pasos:
1. `POST /media/subidas` → devuelve `upload_url` y el `media_url` definitivo (`r2://…`).
2. El cliente hace `PUT` del archivo a `upload_url` con el header `Content-Type` exacto de `headers_requeridos`
   (sin `X-API-Key` ni otros headers; R2 responde `200` sin cuerpo).
3. Llama a `/ingesta/interpretar` (canal `voz`), `/ingesta/cuaderno` o `/webhooks/whatsapp` con `media_url: "r2://…"`.

**Request**
```json
{ "empresa_id": "EMP-0001", "tipo": "audio", "content_type": "audio/ogg", "tamano_bytes": 48213 }
```
- `tipo`: `audio | imagen`. `content_type` permitido por tipo: audio → `audio/ogg`, `audio/webm`, `audio/mpeg`, `audio/mp4`,
  `audio/wav`; imagen → `image/jpeg`, `image/png`, `image/webp`. Los parámetros (`audio/webm;codecs=opus`) se ignoran:
  usa el `Content-Type` que devuelve `headers_requeridos`.
- `tamano_bytes` máximo: 10 MB (audio) y 8 MB (imagen); el valor real se devuelve en `tamano_max_bytes`.

**Response 201**
```json
{
  "media_url": "r2://empresas/EMP-0001/audios/2026/11/0b7c9f0e-6a41-4c52-9d2b-3f1e8a7d5c10.ogg",
  "upload_url": "https://<cuenta>.r2.cloudflarestorage.com/cajaclara-media/empresas/EMP-0001/audios/2026/11/0b7c….ogg?X-Amz-Algorithm=…&X-Amz-Signature=…",
  "metodo": "PUT",
  "headers_requeridos": { "Content-Type": "audio/ogg" },
  "expira_en": "2026-11-14T10:52:00-05:00",
  "tamano_max_bytes": 10485760
}
```
- La URL vale 10 minutos (`R2_PRESIGN_TTL_S`). Si expira, se pide otra.
- El backend solo lee `r2://` con clave bajo `empresas/{empresa_id}/…` de la empresa que consulta; verifica tipo y tamaño
  del objeto antes de descargarlo y borra el temporal tras procesar.

**Errores**: `400 VALIDACION` (tipo, `content_type` o tamaño no permitidos; campos faltantes), `401`, `404 NO_ENCONTRADO`
(empresa), `503 SERVICIO_NO_DISPONIBLE` (R2 sin configurar o caído).

**Configuración del bucket (una vez, en Cloudflare)**
- CORS del bucket: permitir `PUT` desde `http://localhost:5173` (y el dominio de la demo) con `AllowedHeaders: ["Content-Type"]`.
  Ejemplo: `[{"AllowedOrigins":["http://localhost:5173"],"AllowedMethods":["PUT"],"AllowedHeaders":["Content-Type"],"MaxAgeSeconds":3600}]`.
- Recomendado: regla de lifecycle que borre los objetos tras N días (p. ej. 30 en `empresas/`); los audios son datos
  personales y el backend no los necesita después de transcribir.

### 1.1 `POST /webhooks/whatsapp`
Recibe mensajes del proveedor (sandbox de Twilio o chat simulado). Uso interno del bot.

**Request** (formato normalizado por el adaptador del proveedor)
```json
{
  "telefono_hash": "a91f…",
  "empresa_id": "EMP-0001",
  "tipo": "audio",
  "texto": null,
  "media_url": "file://data/audios/demo_001.ogg",
  "recibido_en": "2026-11-14T10:42:00-05:00",
  "mensaje_id": "wamid.123"
}
```
- `tipo`: `texto | audio | imagen | boton`
- Nunca se guarda el número real: solo `telefono_hash`.
- `media_url`: `r2://…` (devuelto por `POST /media/subidas`) o, solo para demo/tests, `file://data/…` y `demo://…`.
  Nunca se aceptan `http(s)://`.

**Response 200**
```json
{
  "respuesta_texto": "Anotado: 2 cervezas, S/ 13.00, efectivo ✅ ¿Correcto?",
  "botones": [
    { "id": "confirmar:BOR-7781", "texto": "✅ Correcto" },
    { "id": "corregir:BOR-7781", "texto": "✏️ Corregir" }
  ],
  "respuesta_audio_url": null
}
```

### 1.2 `POST /ingesta/interpretar`
Convierte texto, audio o foto en un **borrador** de movimiento.

**Request**
```json
{
  "empresa_id": "EMP-0001",
  "canal": "voz",
  "texto": null,
  "media_url": "file://data/audios/demo_001.ogg"
}
```

- `media_url` (canal `voz`): `r2://…` (§1.0) o, solo para demo, `file://data/…` / `demo://…`. Si no se encuentra el
  archivo y no viene `texto` → `422 NO_INTERPRETABLE`; si es de otra empresa o excede tipo/tamaño → `400 VALIDACION`.

**Response 200**
```json
{
  "borrador_id": "BOR-7781",
  "transcripcion": "vendí dos cervezas",
  "movimiento_propuesto": {
    "tipo": "venta",
    "items": [
      { "producto_id": "PRD-0031", "producto": "Cerveza 620 ml", "cantidad": 2, "precio_unitario": 6.50, "subtotal": 13.00 }
    ],
    "monto": 13.00,
    "moneda": "PEN",
    "metodo_pago": "efectivo",
    "contraparte": null,
    "fecha_hora": "2026-11-14T10:42:00-05:00",
    "fecha_vencimiento": null
  },
  "origen_monto": "catalogo",
  "confianza": 0.93,
  "campos_faltantes": [],
  "pregunta_aclaratoria": null,
  "meta": { "modelo": "whisper-small + llm-extractor", "modelo_version": "0.2.0", "prompt_version": "extractor-v3", "fallback_usado": false }
}
```
- `origen_monto`: `dicho_por_usuario | catalogo | estimado`
- Si `confianza < 0.75` o hay `campos_faltantes`, `pregunta_aclaratoria` trae el texto a enviar (ej.: *"¿Fue en efectivo o por billetera?"*).
- Ejemplos de interpretación esperada:

| Frase | `tipo` | Destino al confirmar |
|---|---|---|
| "vendí dos cervezas" | `venta` | `transacciones` |
| "saqué 50 para la casa" | `retiro_personal` | `transacciones` |
| "pagué el colegio de mi hijo" | — | No se registra: el bot explica que la app solo lleva el negocio y pregunta si la plata salió de la caja de la tienda; si es así, se anota como `retiro_personal` |
| "le fié a la señora Carmen 2 panes y una leche" | `venta` + `metodo_pago = credito` | `transacciones` (`afecta_caja = false`) + `cuaderno_fiado` |
| "la señora Carmen me pagó 50" | `cobro_fiado` | `transacciones` (con `fiado_id`) |
| "pedí 2 400 a Andina para pagar el 30" | `compra` + `metodo_pago = credito` | `transacciones` (`afecta_caja = false`) + `deudas` con `tipo = proveedor` (+ dispara chequeo de pedido, §4.5) |
| "me prestaron 1 000, pago 40 diarios" | `prestamo_recibido` | `transacciones` + `deudas` con `tipo = prestamo_informal` |
| "pagué mi RUS, 20 soles" | `pago_impuesto` | `transacciones` + `impuestos` |

Tablas y campos: [modelo_datos.dbml](modelo_datos.dbml) · [diccionario_datos.md](diccionario_datos.md) (§4, cómo se registra cada caso).

### 1.3 `POST /ingesta/confirmar`

**Request**
```json
{
  "borrador_id": "BOR-7781",
  "confirmado": true,
  "correcciones": { "metodo_pago": "billetera_digital" }
}
```

**Response 201**
```json
{
  "movimiento_id": "MOV-000123",
  "registros_creados": [
    { "tabla": "transacciones", "id": "MOV-000123" }
  ],
  "alertas_disparadas": [],
  "saldo_caja_negocio": 2353.00
}
```
- Si `confirmado = false` sin correcciones, el borrador se descarta (`204`).
- Tras guardar, se recalcula el forecast y se evalúan alertas (§6). Las alertas nuevas vuelven en `alertas_disparadas`.

### 1.4 `POST /ingesta/cuaderno` (foto del cuaderno de fiados)

**Request**
```json
{ "empresa_id": "EMP-0001", "media_url": "r2://empresas/EMP-0001/fotos/2026/11/9a1c….jpg" }
```
- `media_url`: `r2://…` (§1.0, `tipo: "imagen"`) o, solo para demo, `file://data/fotos/…` / `demo://fotos/…`.
  La foto se lee con un modelo de visión (VLM) vía OpenRouter (`VLM_MODEL`); la imagen viaja al proveedor como data
  URL base64. Si el VLM no está disponible (sin key, timeout, error o salida inválida) se usa un fixture por nombre
  de foto (`cuaderno_01..03`, `meta.fallback_usado = true`) o, si la foto es desconocida, `fiados_propuestos: []`.
  Las líneas tachadas (ya pagadas) no se proponen: se cuentan en `lineas_tachadas`. Objeto inexistente → `422`;
  ajeno/tipo/tamaño → `400`.

**Response 200**
```json
{
  "borrador_id": "BOR-7790",
  "fiados_propuestos": [
    { "cliente": "Vecina Rosa", "detalle": "pan y huevos", "monto": 12.50, "fecha": "2026-11-12", "confianza": 0.85,
      "cliente_id": "CLI-0110", "cliente_nuevo": false, "posible_duplicado": false },
    { "cliente": "Marcos", "detalle": "fideos y atún", "monto": 8.00, "fecha": "2026-11-10", "confianza": 0.85,
      "cliente_id": null, "cliente_nuevo": true, "posible_duplicado": null }
  ],
  "lineas_no_legibles": 0,
  "lineas_tachadas": 1,
  "meta": { "modelo": "vlm-openrouter", "modelo_version": "openai/gpt-4o-mini", "prompt_version": "cuaderno-v2", "fallback_usado": false }
}
```
Campos extra (opcionales, el front puede ignorarlos): `cliente_id` / `cliente_nuevo` (el nombre se empareja con los
clientes existentes por alias y se devuelve con el nombre del catálogo; si es nuevo se crea recién al confirmar),
`posible_duplicado` (ya existe un fiado igual en `cuaderno_fiado`; al confirmar se omite y vuelve en `duplicados`) y
`lineas_tachadas`. Con fallback a fixture, `meta.modelo = "fixture-cuaderno"`.
Se confirma con `POST /ingesta/confirmar` (puede aceptar o editar cada fiado).

### 1.5 `POST /empresas/{empresa_id}/impuestos`
Registro por menú de botones ("¿Pagaste tu RUS?").

**Request**
```json
{ "periodo": "2026-10", "regimen": "nuevo_rus", "pagado": true, "monto": 20.00, "fecha_pago": "2026-11-12" }
```
**Response 201**
```json
{ "impuesto_id": "IMP-0009", "estado": "al_dia", "proximo_vencimiento": "2026-12-15" }
```

### 1.6 `POST /billeteras/movimientos` (roadmap; en la demo, datos sintéticos)
Movimientos que llegan estructurados. No requieren confirmación.
```json
{
  "empresa_id": "EMP-0001",
  "proveedor_billetera": "billetera_a",
  "operacion_id": "OP-55821",
  "tipo": "ingreso",
  "monto": 18.50,
  "fecha_hora": "2026-11-14T09:12:00-05:00"
}
```
**Response 201** → `{ "movimiento_id": "MOV-000124", "duplicado": false }`

---

## 2. Movimientos (consulta y registro manual)

### 2.1 `GET /empresas/{empresa_id}/movimientos`
Query: `desde`, `hasta`, `tipo`, `categoria`, `canal`, `limit`, `cursor`.

```json
{
  "items": [
    {
      "movimiento_id": "MOV-000123",
      "fecha_hora": "2026-11-14T10:42:00-05:00",
      "tipo": "venta",
      "categoria": "bebidas",
      "monto": 13.00,
      "moneda": "PEN",
      "metodo_pago": "efectivo",
      "contraparte": null,
      "canal": "voz",
      "confianza_extraccion": 0.93,
      "afecta_caja": true,
      "saldo_post": 2353.00
    }
  ],
  "next_cursor": null
}
```

### 2.2 `POST /empresas/{empresa_id}/movimientos`
Registro manual desde la app (`canal = manual`). Mismo esquema que `movimiento_propuesto`. Responde `201` como §1.3.

---

## 3. F2 — Resumen financiero

### `GET /empresas/{empresa_id}/resumen?periodo=2026-11`

```json
{
  "empresa_id": "EMP-0001",
  "periodo": "2026-11",
  "corte": "2026-11-14",
  "indicadores": {
    "saldo_caja_negocio":   { "valor": 2340.00, "variacion_pct": null },
    "ingresos_mes":         { "valor": 8540.00, "variacion_pct": -6.2 },
    "egresos_mes":          { "valor": 7310.00, "variacion_pct": 4.8 },
    "ganancia_neta":        { "valor": 980.00, "variacion_pct": -18.5, "es_aproximada": true, "rango": [760.00, 1210.00] },
    "retiros_personales":   { "valor": 1900.00, "sueldo_fijo_definido": null, "promedio_historico": 1200.00 },
    "pendiente_cobro":      { "valor": 310.00, "n_fiados": 3 },
    "pagos_pendientes":     { "valor": 2420.00, "n_obligaciones": 2 }
  },
  "variacion_vs": "2026-10 al mismo día de corte"
}
```
- `ganancia_neta.es_aproximada = true` cuando faltan costos en el catálogo; entonces se envía `rango`.
- Cálculo determinístico. Sin bloque `meta` de modelo.

---

## 4. F3 y F4 — Forecast, cuentas por cobrar/pagar y simulación

### 4.1 `GET /empresas/{empresa_id}/forecast?horizonte_dias=30`

```json
{
  "empresa_id": "EMP-0001",
  "fecha_corte": "2026-11-14",
  "horizonte_dias": 30,
  "saldo_actual": 2340.00,
  "minimo_operativo": 800.00,
  "serie": [
    { "fecha": "2026-11-15", "ingresos_esperados": 650.00, "egresos_esperados": 380.00, "p10": 2420.00, "p50": 2610.00, "p90": 2790.00 },
    { "fecha": "2026-11-30", "ingresos_esperados": 610.00, "egresos_esperados": 2400.00, "p10": -1180.00, "p50": -650.00, "p90": -90.00 }
  ],
  "dia_critico": {
    "fecha": "2026-11-30",
    "saldo_p50": -650.00,
    "probabilidad_deficit": 0.74,
    "obligacion_asociada": { "tipo": "prestamo_proveedor", "id": "PED-0012", "proveedor": "Distribuidora Andina", "monto": 2400.00 }
  },
  "disponible_para_gastar": {
    "valor": 0.00,
    "formula": "saldo_actual + cobros_esperados − pagos_comprometidos_hasta_proximo_vencimiento − minimo_operativo − reserva_impuestos",
    "componentes": { "saldo_actual": 2340.00, "cobros_esperados": 190.00, "pagos_comprometidos": 2420.00, "minimo_operativo": 800.00, "reserva_impuestos": 20.00 },
    "mensaje": "Hoy no conviene sacar plata para la casa: comprometería el pago del 30/11."
  },
  "ajustes_manuales_aplicados": [],
  "baseline": { "nombre": "naive_estacional", "mae_backtest": 212.40 },
  "modelo_metricas": { "mae_backtest": 158.10, "cobertura_p10_p90": 0.82 },
  "meta": { "modelo": "forecast-lgbm-quantile", "modelo_version": "0.3.1", "fallback_usado": false }
}
```
- `cobros_esperados` ya viene ponderado por la probabilidad de pago de cada fiado (§4.3).
- Si el modelo falla, `meta.fallback_usado = true` y la serie sale del baseline.

### 4.2 `POST /empresas/{empresa_id}/forecast/ajustes`
Ajuste manual de partidas ("este mes no pago alquiler").
```json
{ "fecha": "2026-11-28", "concepto": "alquiler", "monto": 0.00, "motivo": "acuerdo con el dueño del local" }
```
**Response 201** → `{ "ajuste_id": "AJU-0003", "forecast_recalculado": true }`

### 4.3 `GET /empresas/{empresa_id}/fiados?estado=pendiente`

```json
{
  "total_pendiente": 310.00,
  "total_vencido": 215.00,
  "items": [
    {
      "fiado_id": "FIA-0045",
      "cliente_id": "CLI-0102",
      "cliente": "Sra. Carmen",
      "monto": 120.00,
      "fecha": "2026-10-27",
      "dias_transcurridos": 18,
      "estado": "vencido",
      "riesgo_atraso": { "probabilidad": 0.72, "nivel": "alto", "baseline_probabilidad": 0.60 },
      "accion_sugerida": { "tipo": "recordatorio", "texto_boton": "Recordar a la Sra. Carmen" }
    }
  ],
  "meta": { "modelo": "riesgo-atraso-clf", "modelo_version": "0.2.0", "fallback_usado": false }
}
```

**`POST /fiados/{fiado_id}/recordatorio`** → genera el texto a reenviar (no lo envía al vecino):
```json
{ "mensaje": "Hola, Sra. Carmen 😊 Le recuerdo amablemente los S/ 120 pendientes en la bodega. ¡Gracias!" }
```

### 4.4 `GET /empresas/{empresa_id}/pedidos?estado=pendiente`
Préstamos de proveedor (cuentas por pagar). Lee la tabla `deudas` con `tipo = proveedor`; `pedido_id` es su `deuda_id`. `monto_pendiente`, `estado` y `dias_para_vencer` se calculan al momento de responder (no se guardan). Los préstamos de dinero (`tipo ≠ proveedor`) entran al forecast y al asistente; su endpoint de consulta queda como roadmap.
```json
{
  "total_pendiente": 2400.00,
  "items": [
    { "pedido_id": "PED-0012", "proveedor": "Distribuidora Andina", "monto": 2400.00, "monto_pendiente": 2400.00, "fecha_pedido": "2026-11-13", "fecha_vencimiento": "2026-11-30", "estado": "por_vencer", "dias_para_vencer": 16 }
  ],
  "impuestos": { "estado": "al_dia", "proximo_vencimiento": "2026-12-15", "monto_estimado": 20.00 }
}
```

### 4.5 `POST /empresas/{empresa_id}/pedidos/chequeo`
Chequeo **antes de confirmar** un pedido a crédito.

**Request**
```json
{ "proveedor": "Distribuidora Andina", "monto": 2400.00, "fecha_vencimiento": "2026-11-30" }
```

**Response 200**
```json
{
  "saldo_proyectado_al_vencimiento": -650.00,
  "estado_caja": "no_te_alcanza",
  "venta_esperada_periodo": 2000.00,
  "exceso_vs_ventas": 400.00,
  "sugerencias": [
    { "accion": "reducir_pedido", "monto_sugerido": 1800.00, "saldo_resultante": -50.00 },
    { "accion": "pagar_en_partes", "partes": 2, "saldo_resultante": 550.00 },
    { "accion": "combinar", "detalle": "pedir 1 800 + pagar en 2 partes", "saldo_resultante": 850.00 }
  ],
  "fundamento": "En 2 semanas sueles vender alrededor de S/ 2 000 y el 30/11 también vencen otros pagos.",
  "limites": "Proyección basada en tus ventas de los últimos 3 meses; no considera eventos que no hayas registrado.",
  "confianza": "media",
  "meta": { "modelo": "forecast-lgbm-quantile", "modelo_version": "0.3.1", "fallback_usado": false }
}
```

### 4.6 `POST /empresas/{empresa_id}/simular`
Simulador de escenarios (lo usan la app y el asistente).

**Request**
```json
{
  "acciones": [
    { "tipo": "reducir_pedido", "pedido_id": "PED-0012", "nuevo_monto": 1800.00 },
    { "tipo": "pagar_en_partes", "pedido_id": "PED-0012", "partes": 2, "fechas": ["2026-11-30", "2026-12-15"] },
    { "tipo": "cobrar_fiados", "fiado_ids": ["FIA-0045", "FIA-0046", "FIA-0047"], "fecha": "2026-11-20" }
  ]
}
```
- Tipos de acción: `reducir_pedido | pagar_en_partes | diferir_pago | cobrar_fiados | limitar_retiros | ajustar_gasto`

**Response 200**
```json
{
  "sin_acciones": { "saldo_minimo": -650.00, "fecha": "2026-11-30", "estado_caja": "no_te_alcanza" },
  "con_acciones": { "saldo_minimo": 1160.00, "fecha": "2026-11-30", "estado_caja": "te_alcanza" },
  "mejora": 1810.00,
  "serie_con_acciones": [ { "fecha": "2026-11-30", "p50": 1160.00 } ],
  "meta": { "modelo": "simulador-deterministico", "modelo_version": "0.1.0", "fallback_usado": false }
}
```

---

## 5. F5 — Análisis de ingresos y egresos

### `GET /empresas/{empresa_id}/analisis`
Query: `desde`, `hasta`, `agrupar_por` (`categoria | producto | proveedor | cliente_fiado | metodo_pago | mes`), `tipo` (`ingreso | egreso`), `comparar_con` (`periodo_anterior | mismo_periodo_anio_anterior`).

```json
{
  "agrupar_por": "categoria",
  "tipo": "egreso",
  "periodo": { "desde": "2026-11-01", "hasta": "2026-11-14" },
  "grupos": [
    { "clave": "mercaderia", "monto": 4980.00, "participacion_pct": 68.1, "variacion_pct": 12.4 },
    { "clave": "retiros_personales", "monto": 1900.00, "participacion_pct": 26.0, "variacion_pct": 58.3 }
  ],
  "comparacion_pares": {
    "metrica": "retiros_personales_sobre_ventas",
    "valor_empresa": 0.35,
    "mediana_pares": 0.22,
    "grupo_pares": "bodegas · 1–3 trabajadores · Lima Este",
    "n_pares": 120,
    "nota": "Comparación anónima con datos sintéticos."
  }
}
```

---

## 6. F6 — Alertas y nudges

### 6.1 `GET /empresas/{empresa_id}/alertas?estado=activa`

```json
{
  "items": [
    {
      "alerta_id": "ALR-0007",
      "tipo": "faltante_caja",
      "prioridad": 1,
      "creada_en": "2026-11-14T10:42:06-05:00",
      "fecha_evento": "2026-11-30",
      "monto": 650.00,
      "probabilidad": 0.74,
      "nivel_riesgo": "alto",
      "titulo": "El 30/11 no te alcanzará",
      "insight": "Para pagar S/ 2 400 a Distribuidora Andina te faltarían S/ 650.",
      "causas": [
        { "descripcion": "Retiraste más para la casa", "monto": 700.00 },
        { "descripcion": "Pediste más de lo que vendes", "monto": 400.00 },
        { "descripcion": "Fiados sin cobrar", "monto": 310.00 }
      ],
      "accion": { "tipo": "abrir_simulador", "texto_boton": "Ver qué puedo hacer", "payload": { "pedido_id": "PED-0012" } },
      "microexplicacion": "Cuando el dinero de la casa y del negocio se mezclan, es difícil saber cuánto puedes pedir.",
      "canales": ["whatsapp", "app"],
      "estado": "activa",
      "meta": { "modelo": "reglas-alertas + forecast-lgbm-quantile", "modelo_version": "0.3.1", "fallback_usado": false }
    }
  ]
}
```
- Cada alerta lleva: tipo, fecha del problema, monto, probabilidad o nivel de riesgo, causas y una acción.
- Prioridad (1 = más alta): `faltante_caja` → `pedido_excesivo` → `retiro_excesivo` → `obligacion_proxima` → `gasto_inusual`/`caida_ventas` → `fiado_vencido` → `meta_lograda` → `resumen_semanal`.

### 6.2 `POST /alertas/{alerta_id}/accion`
```json
{ "accion": "ejecutada", "detalle": "abrió simulador" }
```
- `accion`: `ejecutada | descartada | posponer`
- **Response 200** → `{ "estado": "atendida" }`

### 6.3 `POST /empresas/{empresa_id}/alertas/evaluar` (interno)
Se llama después de cada movimiento confirmado. Devuelve las alertas nuevas.
- Respeta límites: máximo 2 notificaciones al día por empresa, horario silencioso (21:00–07:00), y ninguna alerta incluye enlaces que pidan credenciales.

### 6.4 `PUT /empresas/{empresa_id}/preferencias-alertas`
```json
{ "canales": ["whatsapp"], "max_por_dia": 2, "silencio_desde": "21:00", "silencio_hasta": "07:00", "resumen_semanal": true }
```

---

## 7. F7 — Asistente financiero

### `POST /empresas/{empresa_id}/asistente/mensajes`

**Request**
```json
{ "conversacion_id": "CNV-0031", "mensaje": "¿Por qué me va a faltar plata a fin de mes?", "canal": "whatsapp" }
```

**Response 200**
```json
{
  "conversacion_id": "CNV-0031",
  "respuesta": "El 30/11 vence tu pago de S/ 2 400 a Distribuidora Andina. Este mes sacaste S/ 700 más de lo usual para la casa, el pedido es S/ 400 mayor a lo que sueles vender y tienes S/ 310 en fiados sin cobrar. Si pides S/ 1 800 y pagas en 2 partes, ese día tendrías S/ 850.",
  "intencion": "explicar_alerta",
  "herramientas_llamadas": [
    { "nombre": "obtener_alertas", "args": { "estado": "activa" } },
    { "nombre": "simular", "args": { "acciones": ["reducir_pedido:1800", "pagar_en_partes:2"] } }
  ],
  "cifras_usadas": [
    { "valor": 2400.00, "fuente": "pedidos.PED-0012.monto" },
    { "valor": 700.00, "fuente": "alertas.ALR-0007.causas[0]" },
    { "valor": 400.00, "fuente": "alertas.ALR-0007.causas[1]" },
    { "valor": 310.00, "fuente": "alertas.ALR-0007.causas[2]" },
    { "valor": 850.00, "fuente": "simular.con_acciones.saldo_minimo" }
  ],
  "verificacion_cifras": { "ok": true, "no_verificadas": [] },
  "fuera_de_alcance": false,
  "ofrecer_humano": true,
  "disclaimer": "Orientación educativa. No es asesoría financiera.",
  "meta": { "modelo": "llm-local", "modelo_version": "qwen2.5-7b-instruct", "prompt_version": "asistente-v2", "fallback_usado": false }
}
```
- `intencion`: `estado_caja | explicar_alerta | simular | concepto | crear_meta | prestamo | fuera_de_alcance | otro`
- Si alguna cifra no se puede verificar, `verificacion_cifras.ok = false` y la respuesta se reemplaza por la plantilla de fallback.
- Si la pregunta pide un crédito o entidad específica, inversión, cripto u opinión tributaria o legal: `fuera_de_alcance = true` con una respuesta educativa y una derivación.

### Herramientas (function calling) disponibles para el LLM
El LLM **no calcula**: solo llama a estas funciones, que envuelven los endpoints anteriores.

| Función | Endpoint que usa |
|---|---|
| `obtener_resumen(periodo)` | `GET /resumen` |
| `obtener_forecast(horizonte_dias)` | `GET /forecast` |
| `obtener_alertas(estado)` | `GET /alertas` |
| `obtener_fiados(estado)` | `GET /fiados` |
| `obtener_pedidos(estado)` | `GET /pedidos` |
| `simular(acciones)` | `POST /simular` |
| `obtener_salud()` | `GET /salud` |
| `crear_meta(plantilla, regla)` | `POST /metas` |
| `explicar_concepto(tema)` | Base de microexplicaciones (texto fijo, revisado por el equipo) |

---

## 8. F8 — Plan de salud y score

### 8.1 `GET /empresas/{empresa_id}/salud`

```json
{
  "score": 71,
  "score_anterior": 64,
  "etapa_actual": "estabilizar",
  "subindicadores": [
    { "id": "constancia_registro", "nombre": "Constancia de registro", "valor": 92, "detalle": "92 días anotando", "peso": 0.20 },
    { "id": "separacion_personal", "nombre": "Separación personal/negocio", "valor": 70, "detalle": "Sueldo fijo de S/ 400 por semana", "peso": 0.20 },
    { "id": "colchon_caja", "nombre": "Colchón de caja", "valor": 45, "detalle": "5 días de gastos cubiertos", "peso": 0.15 },
    { "id": "pedidos_acordes", "nombre": "Pedidos acordes a ventas", "valor": 60, "detalle": "1 de 3 pedidos excedió tus ventas", "peso": 0.15 },
    { "id": "cobro_fiados", "nombre": "Cobro de fiados a tiempo", "valor": 80, "detalle": "80% cobrados a tiempo", "peso": 0.10 },
    { "id": "impuestos_al_dia", "nombre": "Impuestos al día", "valor": 100, "detalle": "Al día", "peso": 0.10 },
    { "id": "meses_sin_faltante", "nombre": "Meses sin faltantes", "valor": 50, "detalle": "1 de 2 meses", "peso": 0.10 }
  ],
  "historial": [ { "mes": "2026-08", "score": 38 }, { "mes": "2026-09", "score": 52 }, { "mes": "2026-10", "score": 64 }, { "mes": "2026-11", "score": 71 } ],
  "rachas": [ { "tipo": "semanas_registrando", "valor": 4 } ],
  "consentimiento_compartir_historial": false,
  "meta": { "modelo": "score-reglas", "modelo_version": "0.1.0", "fallback_usado": false }
}
```
- El score es la suma ponderada de los subindicadores (determinístico y explicable).

### 8.2 `POST /empresas/{empresa_id}/metas`
```json
{
  "plantilla": "apartar_para_pedido",
  "regla": { "tipo": "porcentaje_de_venta", "valor": 0.10, "destino": "fondo_pedidos" },
  "recordatorio": { "frecuencia": "semanal", "dia": "lunes" }
}
```
- Plantillas: `registrar_30_dias | sueldo_fijo | colchon_caja | apartar_para_pedido | reservar_impuestos`
- **Response 201** → `{ "meta_id": "MET-0004", "estado": "activa" }`

### 8.3 `PUT /empresas/{empresa_id}/consentimiento` (roadmap)
```json
{ "compartir_historial_para_evaluacion": true, "alcance": ["resumen_12_meses", "score"], "vigencia_hasta": "2027-05-14" }
```
- Desactivado por defecto. Revocable en cualquier momento. No ofrece ni otorga créditos.

---

## 9. Salud del servicio

### `GET /health`
```json
{
  "estado": "ok",
  "version_api": "1.0.0",
  "componentes": {
    "base_datos": "ok",
    "whisper": { "estado": "ok", "modelo": "faster-whisper-small" },
    "almacenamiento": { "estado": "ok", "bucket": "cajaclara-media" },
    "llm": { "estado": "ok", "modelo": "qwen2.5-7b-instruct", "prompt_versions": { "extractor": "v3", "asistente": "v2", "cuaderno": "v2" } },
    "vlm": { "estado": "ok", "modelo": "openai/gpt-4o-mini", "proveedor": "openrouter" },
    "forecast": { "estado": "ok", "modelo_version": "0.3.1" },
    "riesgo_atraso": { "estado": "ok", "modelo_version": "0.2.0" }
  }
}
```

---

## 10. Mapa endpoint → funcionalidad → responsable

| Funcionalidad | Endpoints | Responsable sugerido |
|---|---|---|
| F1 Ingesta | `/webhooks/whatsapp`, `/media/subidas`, `/ingesta/*`, `/impuestos`, `/billeteras/movimientos` | Backend + GenAI |
| F2 Resumen | `/resumen` | Backend |
| F3 Forecast | `/forecast`, `/forecast/ajustes` | ML |
| F4 Cuentas | `/fiados`, `/fiados/{id}/recordatorio`, `/pedidos`, `/pedidos/chequeo` | ML + Backend |
| Simulador | `/simular` | Backend |
| F5 Análisis | `/analisis` | Datos / BI |
| F6 Alertas | `/alertas`, `/alertas/{id}/accion`, `/alertas/evaluar`, `/preferencias-alertas` | Backend + ML |
| F7 Asistente | `/asistente/mensajes` | GenAI |
| F8 Salud | `/salud`, `/metas`, `/consentimiento` | Backend |
| Operación | `/health` | Backend |

### Mock para trabajar en paralelo
Hasta que los modelos estén listos, el backend publica respuestas fijas con estos mismos JSON (datos de Pedro: saldo S/ 2 340, déficit −S/ 650 el 30/11, pedido S/ 2 400 a Distribuidora Andina, fiados S/ 310). El front y el bot consumen el mock desde el primer momento.
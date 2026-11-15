// Funciones tipadas por endpoint (ver contract.md). Las pantallas solo importan desde aquí.
import { request, empresaId } from './client.js'
import { subirMedia } from './subidas.js'

const emp = (id = empresaId()) => `/empresas/${id}`

export const api = {
  // Sesión de la demo (AUTH_CONTRATO.md). El login es público; un 401 aquí no cierra ninguna sesión.
  login: ({ usuario, contrasena }, { signal, timeoutMs } = {}) =>
    request('POST', '/auth/login', { body: { usuario, contrasena }, idempotent: false, auth: false, signal, timeoutMs }),
  sesion: () => request('GET', '/auth/sesion'),

  // F1 — Ingesta
  interpretar: ({ canal, texto = null, media_url = null }) =>
    request('POST', '/ingesta/interpretar', { body: { empresa_id: empresaId(), canal, texto, media_url } }),
  confirmar: ({ borrador_id, confirmado = true, correcciones = {} }) =>
    request('POST', '/ingesta/confirmar', { body: { borrador_id, confirmado, correcciones } }),
  leerCuaderno: ({ media_url }) =>
    request('POST', '/ingesta/cuaderno', { body: { empresa_id: empresaId(), media_url } }),
  registrarImpuesto: (payload) => request('POST', `${emp()}/impuestos`, { body: payload }),
  // Audios y fotos: POST /media/subidas → PUT directo a R2 → media_url (r2://…) para /chat/mensajes o /ingesta/cuaderno
  subirMedia: (blob, { tipo, contentType }) => subirMedia(blob, { tipo, contentType }),

  // Movimientos
  getMovimientos: (query = {}) => request('GET', `${emp()}/movimientos`, { query }),
  crearMovimiento: (mov) => request('POST', `${emp()}/movimientos`, { body: mov }),

  // F2 — Resumen
  // Sin periodo, el backend usa el mes de su fecha de corte (en la demo, 2026-11-14).
  getResumen: (periodo) => request('GET', `${emp()}/resumen`, { query: { periodo } }),

  // F3 / F4
  getForecast: (horizonte_dias = 30) => request('GET', `${emp()}/forecast`, { query: { horizonte_dias } }),
  ajustarForecast: (ajuste) => request('POST', `${emp()}/forecast/ajustes`, { body: ajuste }),
  getFiados: (estado = 'pendiente') => request('GET', `${emp()}/fiados`, { query: { estado } }),
  recordatorioFiado: (fiado_id) => request('POST', `/fiados/${fiado_id}/recordatorio`, { idempotent: false }),
  getPedidos: (estado = 'pendiente') => request('GET', `${emp()}/pedidos`, { query: { estado } }),
  anularCuenta: ({ tipo, id }) => request('POST', `${emp()}/cuentas/anular`, { body: { tipo, id } }),
  chequearPedido: ({ proveedor, monto, fecha_vencimiento }) =>
    request('POST', `${emp()}/pedidos/chequeo`, { body: { proveedor, monto, fecha_vencimiento }, idempotent: false }),
  simular: (acciones) => request('POST', `${emp()}/simular`, { body: { acciones }, idempotent: false }),

  // F5
  getAnalisis: (query = {}) => request('GET', `${emp()}/analisis`, { query }),

  // F6
  getAlertas: (estado = 'activa') => request('GET', `${emp()}/alertas`, { query: { estado } }),
  accionAlerta: (alerta_id, accion, detalle) =>
    request('POST', `/alertas/${alerta_id}/accion`, { body: { accion, detalle }, idempotent: false }),

  // Chat: el backend decide si el mensaje es un registro, una respuesta al borrador pendiente o una pregunta
  chat: ({ texto, canal = 'texto', media_url = null, borrador_id = null, conversacion_id = null }) =>
    request('POST', `${emp()}/chat/mensajes`, {
      body: { texto, canal, media_url, borrador_id, conversacion_id },
      idempotent: false,
    }),

  // F7
  enviarAsistente: ({ conversacion_id = null, mensaje, canal = 'app' }) =>
    request('POST', `${emp()}/asistente/mensajes`, { body: { conversacion_id, mensaje, canal }, idempotent: false }),

  // F8
  getSalud: () => request('GET', `${emp()}/salud`),
  crearMeta: (meta) => request('POST', `${emp()}/metas`, { body: meta }),

  // Operación
  health: () => request('GET', '/health', { auth: false }),
}

export { ApiError, USE_MOCK, EMPRESA_ID, empresaId, despertarServidor } from './client.js'

// Funciones tipadas por endpoint (ver contract.md). Las pantallas solo importan desde aquí.
import { request, EMPRESA_ID } from './client.js'

const emp = (id = EMPRESA_ID) => `/empresas/${id}`

export const api = {
  // F1 — Ingesta
  interpretar: ({ canal, texto = null, media_url = null }) =>
    request('POST', '/ingesta/interpretar', { body: { empresa_id: EMPRESA_ID, canal, texto, media_url } }),
  confirmar: ({ borrador_id, confirmado = true, correcciones = {} }) =>
    request('POST', '/ingesta/confirmar', { body: { borrador_id, confirmado, correcciones } }),
  leerCuaderno: ({ media_url }) =>
    request('POST', '/ingesta/cuaderno', { body: { empresa_id: EMPRESA_ID, media_url } }),
  registrarImpuesto: (payload) => request('POST', `${emp()}/impuestos`, { body: payload }),

  // Movimientos
  getMovimientos: (query = {}) => request('GET', `${emp()}/movimientos`, { query }),
  crearMovimiento: (mov) => request('POST', `${emp()}/movimientos`, { body: mov }),

  // F2 — Resumen
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

  // F7
  enviarAsistente: ({ conversacion_id = null, mensaje, canal = 'app' }) =>
    request('POST', `${emp()}/asistente/mensajes`, { body: { conversacion_id, mensaje, canal }, idempotent: false }),

  // F8
  getSalud: () => request('GET', `${emp()}/salud`),
  crearMeta: (meta) => request('POST', `${emp()}/metas`, { body: meta }),

  // Operación
  health: () => request('GET', '/health'),
}

export { ApiError, USE_MOCK, EMPRESA_ID } from './client.js'

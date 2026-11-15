// Cliente HTTP de TuCaserito. Un único punto de entrada a la API (contract.md, base /api/v1).
// Por defecto llama al backend FastAPI. Con VITE_USE_MOCK=true las llamadas se resuelven en src/mocks
// (respaldo para una demo sin backend). Los mocks se cargan con import() solo en ese caso: con VITE_USE_MOCK=false
// Vite descarta la rama y los mocks no entran al build.
//
// Autenticación (AUTH_CONTRATO.md): el front no lleva ninguna clave. Cada llamada manda el token de la sesión
// como `Authorization: Bearer`; un 401 borra la sesión y la app vuelve a /ingresar.

import { clearSesion, getSesion } from '../lib/sesion.js'

const env = import.meta.env
export const USE_MOCK = env.VITE_USE_MOCK === 'true'
export const API_BASE = env.VITE_API_BASE || '/api/v1'
/** Solo modo mock: empresa por defecto si la sesión no trae una. Con backend real la empresa sale del token. */
export const EMPRESA_ID = env.VITE_EMPRESA_ID || 'EMP-0001'
/** Empresa actual: la de la sesión (`empresa_id` del login). */
export const empresaId = () => getSesion()?.empresa_id ?? (USE_MOCK ? EMPRESA_ID : null)

/** Error con la forma del contrato: { codigo, mensaje, detalles, request_id, status } (+ retryAfter en segundos si es 429). */
export class ApiError extends Error {
  constructor(status, body, { retryAfter = null } = {}) {
    const e = body?.error ?? {}
    super(e.mensaje || `Error ${status}`)
    this.status = status
    this.codigo = e.codigo || (status === 0 ? 'SIN_CONEXION' : 'DESCONOCIDO')
    this.detalles = e.detalles || []
    this.requestId = e.request_id || null
    this.retryAfter = retryAfter
  }
}

function newIdempotencyKey() {
  return globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`
}

/** Retry-After en segundos (acepta segundos o fecha HTTP). null si no viene o no se puede leer. */
export function parseRetryAfter(valor) {
  if (valor == null || valor === '') return null
  const n = Number(valor)
  if (Number.isFinite(n)) return Math.max(0, Math.ceil(n))
  const fecha = Date.parse(valor)
  return Number.isNaN(fecha) ? null : Math.max(0, Math.ceil((fecha - Date.now()) / 1000))
}

/** Un 401 en una ruta protegida significa token vencido o inválido: se cierra la sesión (RequireAuth lleva al login). */
function sesionRechazada(status, auth) {
  if (auth && status === 401) clearSesion('expirada')
}

/**
 * request('GET', '/empresas/EMP-0001/resumen', { query: { periodo: '2026-11' } })
 * Los POST que crean registros mandan Idempotency-Key automáticamente.
 * auth=false: ruta pública (login, health): no manda el token y un 401 no cierra la sesión.
 * timeoutMs: corta la espera y lanza ApiError(0, TIEMPO_AGOTADO).
 */
export async function request(
  method,
  path,
  { query, body, idempotent = method === 'POST', signal, auth = true, timeoutMs } = {},
) {
  const qs = query
    ? '?' +
      new URLSearchParams(
        Object.entries(query).filter(([, v]) => v !== undefined && v !== null && v !== ''),
      ).toString()
    : ''
  const token = auth ? getSesion()?.token : null

  // La condición usa import.meta.env directamente (no USE_MOCK) para que el build elimine esta rama por completo.
  if (import.meta.env.VITE_USE_MOCK === 'true') {
    const { mockRequest } = await import('../mocks/handlers.js')
    const res = await mockRequest(method, path, { query: query || {}, body, token })
    if (res.status >= 400) {
      sesionRechazada(res.status, auth)
      throw new ApiError(res.status, res.body, { retryAfter: parseRetryAfter(res.headers?.['Retry-After']) })
    }
    return res.body
  }

  const headers = { Accept: 'application/json' }
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  if (token) headers.Authorization = `Bearer ${token}`
  if (idempotent) headers['Idempotency-Key'] = newIdempotencyKey()

  const ctrl = new AbortController()
  const onAbort = () => ctrl.abort(signal.reason)
  if (signal) {
    if (signal.aborted) ctrl.abort(signal.reason)
    else signal.addEventListener('abort', onAbort, { once: true })
  }
  let vencido = false
  const timer = timeoutMs
    ? setTimeout(() => {
        vencido = true
        ctrl.abort()
      }, timeoutMs)
    : null

  let res
  try {
    res = await fetch(`${API_BASE}${path}${qs}`, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
      signal: ctrl.signal,
    })
  } catch (err) {
    if (vencido) {
      throw new ApiError(0, {
        error: { codigo: 'TIEMPO_AGOTADO', mensaje: 'El servidor no respondió a tiempo. Intenta otra vez en un momento.' },
      })
    }
    if (err.name === 'AbortError') throw err
    throw new ApiError(0, { error: { mensaje: 'No hay conexión. Revisa tu internet e intenta otra vez.' } })
  } finally {
    if (timer) clearTimeout(timer)
    signal?.removeEventListener('abort', onAbort)
  }

  if (res.status === 204) return null
  const data = await res.json().catch(() => null)
  if (!res.ok) {
    sesionRechazada(res.status, auth)
    throw new ApiError(res.status, data, { retryAfter: parseRetryAfter(res.headers.get('Retry-After')) })
  }
  return data
}

/**
 * Despierta el backend sin esperar respuesta (Render free lo duerme tras un rato sin tráfico).
 * Se llama al abrir la landing y el login, para que el primer "Ingresar" no espere el arranque entero.
 */
export function despertarServidor() {
  if (import.meta.env.VITE_USE_MOCK === 'true') return
  fetch(`${API_BASE}/health`, { method: 'GET', headers: { Accept: 'application/json' } }).catch(() => {})
}

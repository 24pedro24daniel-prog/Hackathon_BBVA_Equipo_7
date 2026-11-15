// Cliente HTTP de TuCaserito. Un único punto de entrada a la API (contract.md, base /api/v1).
// Con VITE_USE_MOCK=true (por defecto) las llamadas se resuelven en src/mocks con los mismos JSON del contrato,
// así el front funciona sin backend y conectar el backend real es solo cambiar la variable de entorno.

import { mockRequest } from '../mocks/handlers.js'

const env = import.meta.env
export const USE_MOCK = (env.VITE_USE_MOCK ?? 'true') !== 'false'
export const API_BASE = env.VITE_API_BASE || '/api/v1'
export const EMPRESA_ID = env.VITE_EMPRESA_ID || 'EMP-0001'
const API_KEY = env.VITE_API_KEY || ''

/** Error con la forma del contrato: { codigo, mensaje, detalles, request_id, status } */
export class ApiError extends Error {
  constructor(status, body) {
    const e = body?.error ?? {}
    super(e.mensaje || `Error ${status}`)
    this.status = status
    this.codigo = e.codigo || (status === 0 ? 'SIN_CONEXION' : 'DESCONOCIDO')
    this.detalles = e.detalles || []
    this.requestId = e.request_id || null
  }
}

function newIdempotencyKey() {
  return globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`
}

/**
 * request('GET', '/empresas/EMP-0001/resumen', { query: { periodo: '2026-11' } })
 * Los POST que crean registros mandan Idempotency-Key automáticamente.
 */
export async function request(method, path, { query, body, idempotent = method === 'POST', signal } = {}) {
  const qs = query
    ? '?' +
      new URLSearchParams(
        Object.entries(query).filter(([, v]) => v !== undefined && v !== null && v !== ''),
      ).toString()
    : ''

  if (USE_MOCK) {
    const res = await mockRequest(method, path, { query: query || {}, body })
    if (res.status >= 400) throw new ApiError(res.status, res.body)
    return res.body
  }

  const headers = { Accept: 'application/json' }
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  if (API_KEY) headers['X-API-Key'] = API_KEY
  if (idempotent) headers['Idempotency-Key'] = newIdempotencyKey()

  let res
  try {
    res = await fetch(`${API_BASE}${path}${qs}`, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
      signal,
    })
  } catch (err) {
    if (err.name === 'AbortError') throw err
    throw new ApiError(0, { error: { mensaje: 'No hay conexión. Revisa tu internet e intenta otra vez.' } })
  }

  if (res.status === 204) return null
  const data = await res.json().catch(() => null)
  if (!res.ok) throw new ApiError(res.status, data)
  return data
}

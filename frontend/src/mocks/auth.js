// Login de las demos sin backend (VITE_USE_MOCK=true). Imita AUTH_CONTRATO.md: mismos códigos de error, 429 con
// Retry-After, 401 con token vencido o ausente y 403 si se pide otra empresa. Solo entra al build en modo mock.
// Las contraseñas no se guardan: solo el SHA-256 de "usuario:contraseña".

import { getSesion } from '../lib/sesion.js'

const TTL_S = 8 * 60 * 60
const MAX_FALLOS = 5
const VENTANA_MS = 5 * 60 * 1000
const BLOQUEO_S = 30

const DEMOS = {
  demo1: {
    hash: '75fc3e526758bb67c14cb377782c09ee6c535b08f094b9e58e14d71c66ec5934',
    empresa_id: import.meta.env.VITE_EMPRESA_ID || 'EMP-0001',
    nombre: 'Bodega Don Pedro',
    escenario: 'pedro',
  },
  demo2: {
    hash: '0f7eb68f09a7790ee1536efefdd196b53bb64e7b1aebdc1dd330f253378980d4',
    empresa_id: 'EMP-0030',
    nombre: 'Bodega SurAndina',
    escenario: 'sano',
  },
  demo3: {
    hash: 'ea68183e371aa21e7aa8711df5002bf22e1e83fef944dde5e049429bd54b5a1c',
    empresa_id: 'EMP-0002',
    nombre: 'Bodega Nueva Esperanza',
    escenario: 'nuevo',
  },
}

const reqId = () => `req_${Math.random().toString(16).slice(2, 8)}`
const err = (status, codigo, mensaje, headers) => ({
  status,
  body: { error: { codigo, mensaje, detalles: [], request_id: reqId() } },
  ...(headers ? { headers } : {}),
})

/** Escenario de datos de la sesión actual: 'pedro' | 'sano' | 'nuevo'. */
export function escenarioDeSesion() {
  return DEMOS[getSesion()?.usuario]?.escenario ?? 'pedro'
}

// ---------- SHA-256 ----------
// crypto.subtle solo existe en contextos seguros (https o localhost); en la red local por http se usa la versión JS.
async function sha256Hex(texto) {
  const bytes = new TextEncoder().encode(texto)
  if (globalThis.crypto?.subtle) {
    const buf = await crypto.subtle.digest('SHA-256', bytes)
    return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, '0')).join('')
  }
  return sha256Js(bytes)
}

function sha256Js(bytes) {
  const K = []
  const H = []
  const primo = (n) => { for (let d = 2; d * d <= n; d++) if (n % d === 0) return false; return true }
  for (let n = 2, i = 0; i < 64; n++) {
    if (!primo(n)) continue
    if (i < 8) H[i] = (Math.pow(n, 1 / 2) * 2 ** 32) | 0
    K[i++] = (Math.pow(n, 1 / 3) * 2 ** 32) | 0
  }
  const len = bytes.length
  const total = (((len + 9) >> 6) + 1) << 6
  const m = new Uint8Array(total)
  m.set(bytes)
  m[len] = 0x80
  const view = new DataView(m.buffer)
  view.setUint32(total - 4, len * 8)
  view.setUint32(total - 8, Math.floor((len * 8) / 2 ** 32))
  const w = new Int32Array(64)
  const rot = (x, n) => (x >>> n) | (x << (32 - n))
  for (let off = 0; off < total; off += 64) {
    for (let t = 0; t < 16; t++) w[t] = view.getInt32(off + t * 4)
    for (let t = 16; t < 64; t++) {
      const s0 = rot(w[t - 15], 7) ^ rot(w[t - 15], 18) ^ (w[t - 15] >>> 3)
      const s1 = rot(w[t - 2], 17) ^ rot(w[t - 2], 19) ^ (w[t - 2] >>> 10)
      w[t] = (w[t - 16] + s0 + w[t - 7] + s1) | 0
    }
    let [a, b, c, d, e, f, g, h] = H
    for (let t = 0; t < 64; t++) {
      const t1 = (h + (rot(e, 6) ^ rot(e, 11) ^ rot(e, 25)) + ((e & f) ^ (~e & g)) + K[t] + w[t]) | 0
      const t2 = ((rot(a, 2) ^ rot(a, 13) ^ rot(a, 22)) + ((a & b) ^ (a & c) ^ (b & c))) | 0
      h = g; g = f; f = e; e = (d + t1) | 0; d = c; c = b; b = a; a = (t1 + t2) | 0
    }
    H[0] = (H[0] + a) | 0; H[1] = (H[1] + b) | 0; H[2] = (H[2] + c) | 0; H[3] = (H[3] + d) | 0
    H[4] = (H[4] + e) | 0; H[5] = (H[5] + f) | 0; H[6] = (H[6] + g) | 0; H[7] = (H[7] + h) | 0
  }
  return H.map((x) => (x >>> 0).toString(16).padStart(8, '0')).join('')
}

// ---------- Token (sin firma: es un mock; el real lo firma el backend con HMAC) ----------
const b64 = (obj) => btoa(JSON.stringify(obj)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
const deB64 = (s) => JSON.parse(atob(s.replace(/-/g, '+').replace(/_/g, '/')))

function leerToken(token) {
  if (typeof token !== 'string' || !token.startsWith('mock.')) return { error: 'NO_AUTORIZADO' }
  try {
    const p = deB64(token.slice(5))
    if (!DEMOS[p.sub] || DEMOS[p.sub].empresa_id !== p.emp) return { error: 'NO_AUTORIZADO' }
    if (typeof p.exp !== 'number' || p.exp * 1000 <= Date.now()) return { error: 'SESION_EXPIRADA' }
    return { payload: p }
  } catch {
    return { error: 'NO_AUTORIZADO' }
  }
}

// ---------- Límite de intentos (en memoria, como el backend con una instancia) ----------
let fallos = []
let bloqueadoHasta = 0

async function login(body) {
  const ahora = Date.now()
  if (bloqueadoHasta > ahora) {
    const s = Math.ceil((bloqueadoHasta - ahora) / 1000)
    return err(429, 'DEMASIADOS_INTENTOS', 'Demasiados intentos. Espera un momento y vuelve a intentar.', { 'Retry-After': String(s) })
  }
  const { usuario, contrasena } = body ?? {}
  const textoValido = (v) => typeof v === 'string' && v.length >= 1 && v.length <= 64
  if (!textoValido(usuario) || !textoValido(contrasena)) {
    return err(422, 'VALIDACION', 'Revisa el usuario y la contraseña.')
  }
  const demo = DEMOS[usuario.trim().toLowerCase()]
  const hash = await sha256Hex(`${usuario.trim().toLowerCase()}:${contrasena}`)
  if (!demo || hash !== demo.hash) {
    fallos = [...fallos.filter((t) => ahora - t < VENTANA_MS), ahora]
    if (fallos.length >= MAX_FALLOS) {
      fallos = []
      bloqueadoHasta = ahora + BLOQUEO_S * 1000
      return err(429, 'DEMASIADOS_INTENTOS', 'Demasiados intentos. Espera un momento y vuelve a intentar.', {
        'Retry-After': String(BLOQUEO_S),
      })
    }
    return err(401, 'CREDENCIALES_INVALIDAS', 'Usuario o contraseña incorrectos.')
  }
  const sub = usuario.trim().toLowerCase()
  const exp = Math.floor(ahora / 1000) + TTL_S
  return {
    status: 200,
    body: {
      token: `mock.${b64({ sub, emp: demo.empresa_id, iat: Math.floor(ahora / 1000), exp })}`,
      tipo: 'Bearer',
      expira_en: TTL_S,
      expira: new Date(exp * 1000).toISOString(),
      usuario: sub,
      empresa_id: demo.empresa_id,
      negocio: { nombre: demo.nombre },
    },
  }
}

/**
 * Rutas de autenticación y control de acceso del mock.
 * Devuelve una respuesta si la petición termina aquí (login, sesión, 401, 403) o null si sigue a los handlers de datos.
 */
export async function autenticar(method, path, { body, token }) {
  if (method === 'POST' && path === '/auth/login') return login(body)
  if (path === '/health') return null

  const { payload, error } = leerToken(token)
  if (error === 'SESION_EXPIRADA') return err(401, 'SESION_EXPIRADA', 'Tu sesión venció. Ingresa otra vez.')
  if (error) return err(401, 'NO_AUTORIZADO', 'Necesitas ingresar para ver esto.')

  if (method === 'GET' && path === '/auth/sesion') {
    const demo = DEMOS[payload.sub]
    return {
      status: 200,
      body: { usuario: payload.sub, empresa_id: payload.emp, expira: new Date(payload.exp * 1000).toISOString(), negocio: { nombre: demo.nombre } },
    }
  }

  // El token solo sirve para su empresa: en la ruta o en el cuerpo.
  const enRuta = path.match(/\/empresas\/([^/]+)/)?.[1]
  const enCuerpo = body?.empresa_id
  if ((enRuta && enRuta !== payload.emp) || (enCuerpo && enCuerpo !== payload.emp)) {
    return err(403, 'EMPRESA_NO_PERMITIDA', 'No tienes permiso para ver los datos de ese negocio.')
  }
  return null
}

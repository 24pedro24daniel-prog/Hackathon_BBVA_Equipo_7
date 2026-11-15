// Sesión de la demo (AUTH_CONTRATO.md): el token del login vive en sessionStorage ('tucaserito-sesion'),
// se manda como `Authorization: Bearer` y decide la empresa (empresa_id). Se borra al cerrar la pestaña,
// al tocar "Cerrar sesión" o cuando el backend responde 401.
// Todo el acceso al storage va con try/catch: si está bloqueado, la sesión dura mientras la página siga abierta.

const KEY = 'tucaserito-sesion'
const EVENTO = 'tucaserito-sesion'

let enMemoria = null // respaldo si sessionStorage no está disponible
let motivoSalida = null // por qué se cerró la sesión ('expirada' | 'salir'); el login lo explica

function leer() {
  try {
    const raw = sessionStorage.getItem(KEY)
    if (raw) return JSON.parse(raw)
  } catch {
    /* storage bloqueado o JSON inválido: se usa la copia en memoria */
  }
  return enMemoria
}

function valida(s) {
  if (!s || typeof s.token !== 'string' || !s.token || typeof s.empresa_id !== 'string') return false
  // Si el backend mandó la hora de vencimiento y ya pasó, la sesión no sirve (el backend respondería 401).
  const vence = s.expira ? Date.parse(s.expira) : NaN
  return Number.isNaN(vence) || vence > Date.now()
}

/** { token, usuario, empresa_id, expira, negocio: { nombre } } o null. */
export function getSesion() {
  const s = leer()
  if (valida(s)) return s
  if (s) borrar()
  return null
}

function avisar(sesion) {
  window.dispatchEvent(new CustomEvent(EVENTO, { detail: sesion }))
}

function borrar() {
  enMemoria = null
  try {
    sessionStorage.removeItem(KEY)
  } catch {
    /* sin storage: basta con la copia en memoria */
  }
}

/** Guarda la respuesta de POST /auth/login (solo los campos que el front usa). */
export function setSesion(login) {
  const sesion = {
    token: login.token,
    usuario: login.usuario,
    empresa_id: login.empresa_id,
    expira: login.expira ?? (login.expira_en ? new Date(Date.now() + login.expira_en * 1000).toISOString() : null),
    negocio: { nombre: login.negocio?.nombre ?? null, ...(login.negocio?.duenio ? { duenio: login.negocio.duenio } : {}) },
  }
  enMemoria = sesion
  try {
    sessionStorage.setItem(KEY, JSON.stringify(sesion))
  } catch {
    /* sin storage: la sesión dura hasta recargar */
  }
  motivoSalida = null
  avisar(sesion)
  return sesion
}

/** Cierra la sesión. motivo: 'salir' (el usuario la cerró) | 'expirada' (el backend respondió 401). */
export function clearSesion(motivo = 'salir') {
  const habia = leer() != null
  borrar()
  if (habia) motivoSalida = motivo
  avisar(null)
}

/** Por qué terminó la última sesión ('salir' | 'expirada' | null), para explicarlo en el login. Se limpia al volver a entrar. */
export function ultimoMotivoSalida() {
  return motivoSalida
}

export const EVENTO_SESION = EVENTO

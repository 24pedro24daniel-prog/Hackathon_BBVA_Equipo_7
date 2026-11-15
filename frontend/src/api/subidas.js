// Subida de audios y fotos a Cloudflare R2 (contract.md §1.0), en 3 pasos:
//   1. POST /media/subidas (con la sesión) → upload_url prefirmada + media_url definitivo (r2://…)
//   2. PUT del archivo directo a upload_url con el Content-Type exacto de headers_requeridos (sin token: va a R2, no al backend)
//   3. Quien llama usa media_url en /chat/mensajes (voz) o /ingesta/cuaderno (foto)
// Los errores salen como ApiError con un `mensaje` escrito para Pedro y `paraPedro = true`.

import { ApiError, empresaId, request } from './client.js'

/** Error de subida con texto para mostrar en el chat. */
function errorSubida(status, codigo, mensaje, extra = {}) {
  const e = new ApiError(status, { error: { codigo, mensaje } }, extra)
  e.paraPedro = true
  return e
}

const QUE = { audio: 'audios', imagen: 'fotos' }

/** Traduce los errores de POST /media/subidas a un texto para Pedro. */
function traducirError(err, tipo) {
  if (err?.status === 503) {
    return errorSubida(503, 'SERVICIO_NO_DISPONIBLE', `Ahora no puedo recibir ${QUE[tipo]}. ${tipo === 'audio' ? 'Escríbeme tu mensaje, por favor.' : 'Intenta en un rato.'}`)
  }
  if (err?.status === 429) {
    const s = err.retryAfter
    return errorSubida(429, 'DEMASIADOS_INTENTOS', s ? `Mandaste muchos mensajes seguidos. Espera ${s} s y vuelve a intentar.` : 'Mandaste muchos mensajes seguidos. Espera un momento y vuelve a intentar.', { retryAfter: s })
  }
  if (err?.status === 400 || err?.status === 413 || err?.status === 415) {
    // El backend ya explica el problema (tipo o tamaño no permitido)
    return errorSubida(err.status, err.codigo || 'VALIDACION', err.message || `No puedo recibir ese archivo.`)
  }
  return err
}

async function putR2({ upload_url, headers_requeridos }, blob) {
  let res
  try {
    res = await fetch(upload_url, { method: 'PUT', headers: headers_requeridos, body: blob })
  } catch {
    // Sin conexión o bloqueado por CORS del bucket (el navegador no distingue)
    throw errorSubida(0, 'SUBIDA_FALLIDA', 'No pude subir el archivo. Revisa tu conexión e intenta otra vez.')
  }
  return res.status
}

/**
 * Sube un Blob y devuelve su media_url (r2://…).
 * tipo: 'audio' | 'imagen'; contentType: tipo base aceptado por el backend (audio/webm, image/jpeg…).
 */
export async function subirMedia(blob, { tipo, contentType }) {
  const pedir = () =>
    request('POST', '/media/subidas', {
      body: { empresa_id: empresaId(), tipo, content_type: contentType, tamano_bytes: blob.size },
      idempotent: false,
    }).catch((err) => {
      throw traducirError(err, tipo)
    })

  let subida = await pedir()

  // Modo mock: no hay R2; se simula el tiempo de subida.
  if (import.meta.env.VITE_USE_MOCK === 'true') {
    await new Promise((r) => setTimeout(r, 500))
    return subida.media_url
  }

  let status = await putR2(subida, blob)
  // 403: la URL prefirmada venció (o la firma no calza). Se pide otra una sola vez.
  if (status === 403 || status === 400) {
    subida = await pedir()
    status = await putR2(subida, blob)
  }
  if (status === 413) throw errorSubida(413, 'MUY_GRANDE', 'El archivo es muy pesado. Prueba con uno más chico.')
  if (status < 200 || status >= 300) {
    throw errorSubida(status, 'SUBIDA_FALLIDA', 'No pude subir el archivo. Intenta otra vez en un momento.')
  }
  return subida.media_url
}

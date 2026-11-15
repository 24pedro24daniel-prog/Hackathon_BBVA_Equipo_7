// Entrada de voz y foto del chat.
// - Voz real: getUserMedia + MediaRecorder (useGrabadora.js). Se sube a R2 (api.subirMedia) y el backend la transcribe (Whisper).
// - Foto real: <input type="file" accept="image/*" capture="environment">, se achica en el navegador (lado mayor 1600 px,
//   JPEG) y se sube a R2; el backend la lee con el modelo de visión.
// - Notas y foto de prueba (demo://): las usan los guiones de demo (demoScripts.js) y la alternativa cuando el navegador no
//   puede grabar. El backend usa el `texto` como transcripción y la foto `cuaderno_01` tiene lectura precalculada.

export const DEMO_VOICE_NOTES = [
  { id: 'cervezas', texto: 'vendí dos cervezas', duracion: '0:04', media_url: 'demo://audios/vendi_dos_cervezas.ogg' },
  { id: 'rus', texto: 'pagué mi RUS, 20 soles', duracion: '0:03', media_url: 'demo://audios/pague_mi_rus.ogg' },
  { id: 'andina', texto: 'pedí 2400 a andina para el 30', duracion: '0:05', media_url: 'demo://audios/pedi_2400_andina.ogg' },
]

export const DEMO_CUADERNO = {
  media_url: 'demo://fotos/cuaderno_01.jpg',
  caption: 'mi cuaderno de fiados',
}

// Límites (espejo de backend/parametros.env; el backend vuelve a validar)
export const AUDIO_MAX_S = 60
export const AUDIO_MIN_S = 1
export const AUDIO_MAX_BYTES = 10 * 1024 * 1024 // MEDIA_MAX_AUDIO_BYTES
export const IMAGEN_MAX_BYTES = 8 * 1024 * 1024 // MEDIA_MAX_IMAGEN_BYTES
export const IMAGEN_LADO_MAX = 1600
const TIPOS_AUDIO = ['audio/ogg', 'audio/webm', 'audio/mpeg', 'audio/mp4', 'audio/wav'] // MEDIA_TIPOS_AUDIO

/** Nota de voz de prueba (guiones de demo): el backend usa `texto` como transcripción. */
export async function capturarNotaDeVoz(demoNote) {
  return { texto: demoNote.texto, media_url: demoNote.media_url, duracion: demoNote.duracion }
}

/** Foto de prueba (guion "fiados"): lectura precalculada en el backend. */
export async function capturarFotoCuaderno() {
  return { ...DEMO_CUADERNO }
}

/** 'audio/webm;codecs=opus' → 'audio/webm' */
export const tipoBase = (mime) => (mime || '').split(';', 1)[0].trim().toLowerCase()

/** ¿Este navegador puede grabar? (necesita https o localhost, getUserMedia y MediaRecorder) */
export function puedeGrabar() {
  return (
    typeof window !== 'undefined' &&
    window.isSecureContext !== false &&
    !!navigator.mediaDevices?.getUserMedia &&
    typeof window.MediaRecorder === 'function'
  )
}

/**
 * Formato de grabación soportado por el navegador y aceptado por el backend.
 * Chrome/Edge/Firefox graban Opus en WebM u Ogg; Safari graba AAC en MP4. null = dejar que el navegador elija.
 */
export function elegirFormatoAudio() {
  const candidatos = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus', 'audio/ogg', 'audio/mp4', 'audio/mpeg', 'audio/wav']
  const ok = (t) => {
    try {
      return window.MediaRecorder.isTypeSupported?.(t)
    } catch {
      return false
    }
  }
  return candidatos.find(ok) ?? null
}

export const audioAceptado = (mime) => TIPOS_AUDIO.includes(tipoBase(mime))

/** Error de captura con un mensaje claro para Pedro. */
export class ErrorCaptura extends Error {
  constructor(codigo, mensaje) {
    super(mensaje)
    this.codigo = codigo
  }
}

/** Traduce los errores de getUserMedia / MediaRecorder. */
export function errorDeMicrofono(err) {
  switch (err?.name) {
    case 'NotAllowedError':
    case 'SecurityError':
      return new ErrorCaptura(
        'permiso',
        'No tengo permiso para usar el micrófono. Actívalo en la configuración del navegador (el ícono junto a la dirección) o escríbeme tu mensaje.',
      )
    case 'NotFoundError':
    case 'OverconstrainedError':
      return new ErrorCaptura('sin_microfono', 'No encontré un micrófono en este equipo. Escríbeme tu mensaje.')
    case 'NotReadableError':
    case 'AbortError':
      return new ErrorCaptura('ocupado', 'El micrófono está ocupado por otra aplicación. Ciérrala o escríbeme tu mensaje.')
    default:
      return new ErrorCaptura('desconocido', 'No pude usar el micrófono. Escríbeme tu mensaje, por favor.')
  }
}

export const duracionTexto = (s) => {
  const t = Math.max(0, Math.round(s))
  return `${Math.floor(t / 60)}:${String(t % 60).padStart(2, '0')}`
}

/** Decodifica la foto respetando la orientación EXIF (createImageBitmap) o con <img> como respaldo. */
async function decodificar(file) {
  if (typeof createImageBitmap === 'function') {
    try {
      return await createImageBitmap(file, { imageOrientation: 'from-image' })
    } catch {
      /* algunos navegadores no aceptan la opción o el formato: se prueba con <img> */
    }
  }
  const url = URL.createObjectURL(file)
  try {
    const img = new Image()
    img.decoding = 'async'
    img.src = url
    await img.decode()
    return img
  } finally {
    URL.revokeObjectURL(url)
  }
}

const aBlob = (canvas, calidad) =>
  new Promise((resolve, reject) =>
    canvas.toBlob((b) => (b ? resolve(b) : reject(new Error('toBlob'))), 'image/jpeg', calidad),
  )

/**
 * Achica la foto en el navegador antes de subirla: lado mayor ≤ 1600 px, JPEG.
 * Menos datos móviles, subida más rápida y menos costo del modelo de visión. Devuelve { blob, contentType, ancho, alto }.
 */
export async function prepararFoto(file) {
  if (!file || !/^image\//.test(file.type || 'image/')) {
    throw new ErrorCaptura('formato', 'Eso no parece una foto. Elige una imagen (JPG o PNG).')
  }
  let fuente
  try {
    fuente = await decodificar(file)
  } catch {
    throw new ErrorCaptura('formato', 'No pude abrir esa foto. Prueba con otra (JPG o PNG).')
  }
  const w0 = fuente.width || fuente.naturalWidth
  const h0 = fuente.height || fuente.naturalHeight
  const escala = Math.min(1, IMAGEN_LADO_MAX / Math.max(w0, h0))
  const ancho = Math.max(1, Math.round(w0 * escala))
  const alto = Math.max(1, Math.round(h0 * escala))
  const canvas = document.createElement('canvas')
  canvas.width = ancho
  canvas.height = alto
  const ctx = canvas.getContext('2d')
  ctx.fillStyle = '#ffffff' // fondo blanco por si la imagen trae transparencia
  ctx.fillRect(0, 0, ancho, alto)
  ctx.drawImage(fuente, 0, 0, ancho, alto)
  fuente.close?.()
  let blob = await aBlob(canvas, 0.82)
  for (const calidad of [0.7, 0.55]) {
    if (blob.size <= IMAGEN_MAX_BYTES) break
    blob = await aBlob(canvas, calidad)
  }
  if (blob.size > IMAGEN_MAX_BYTES) throw new ErrorCaptura('pesada', 'La foto es muy pesada. Prueba con otra.')
  return { blob, contentType: 'image/jpeg', ancho, alto }
}

// Entrada de voz y foto del chat simulado.
// Aún no se graba ni se sube nada: el micrófono ofrece notas de voz de prueba y la cámara una foto fija.
// El backend acepta canal 'voz' con `texto` + un media_url que no existe (usa el texto como transcripción), y
// para la foto `cuaderno_01` responde con la lectura precalculada de la demo cuando no hay modelo de visión.

export const DEMO_VOICE_NOTES = [
  { id: 'cervezas', texto: 'vendí dos cervezas', duracion: '0:04', media_url: 'demo://audios/vendi_dos_cervezas.ogg' },
  { id: 'rus', texto: 'pagué mi RUS, 20 soles', duracion: '0:03', media_url: 'demo://audios/pague_mi_rus.ogg' },
  { id: 'andina', texto: 'pedí 2400 a andina para el 30', duracion: '0:05', media_url: 'demo://audios/pedi_2400_andina.ogg' },
]

export const DEMO_CUADERNO = {
  media_url: 'demo://fotos/cuaderno_01.jpg',
  caption: 'mi cuaderno de fiados',
}

/**
 * Límite único entre "capturar audio" y "interpretar". Devuelve lo que se manda a POST /ingesta/interpretar.
 *
 * TODO(voz-real): reemplazar por grabación real:
 *   1. navigator.mediaDevices.getUserMedia({ audio: true }) + new MediaRecorder(stream) mientras se mantiene el botón.
 *   2. POST /media/subidas { empresa_id, tipo: 'audio', content_type, tamano_bytes } → { media_url, upload_url, headers_requeridos };
 *      PUT del Blob a upload_url (requiere R2 configurado en el backend; si no, responde 503).
 *   3. Devolver { texto: null, media_url, duracion } — el backend transcribe (whisper) y responde `transcripcion`.
 * El resto del flujo (burbuja de audio, "Escuchando tu audio…", tarjeta de confirmación) no cambia.
 */
export async function capturarNotaDeVoz(demoNote) {
  return { texto: demoNote.texto, media_url: demoNote.media_url, duracion: demoNote.duracion }
}

/**
 * TODO(foto-real): <input type="file" accept="image/*" capture="environment"> → POST /media/subidas (tipo 'imagen') → PUT
 * → devolver su media_url. Leer una foto real necesita además el modelo de visión configurado (OPENROUTER_API_KEY).
 */
export async function capturarFotoCuaderno() {
  return { ...DEMO_CUADERNO }
}

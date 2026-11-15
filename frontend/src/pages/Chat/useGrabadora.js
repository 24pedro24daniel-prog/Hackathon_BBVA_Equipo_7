// Grabación de notas de voz con getUserMedia + MediaRecorder.
// const g = useGrabadora({ onListo }) → g.estado ('inactivo' | 'pidiendo' | 'grabando'), g.segundos, g.error,
// g.iniciar(), g.detener() (termina y entrega la nota a onListo), g.cancelar() (descarta), g.limpiarError().
// Corta sola al llegar a AUDIO_MAX_S. Libera el micrófono al terminar o al desmontar.
import { useCallback, useEffect, useRef, useState } from 'react'
import {
  AUDIO_MAX_BYTES,
  AUDIO_MAX_S,
  AUDIO_MIN_S,
  ErrorCaptura,
  audioAceptado,
  elegirFormatoAudio,
  errorDeMicrofono,
  puedeGrabar,
  tipoBase,
} from './media.js'

export function useGrabadora({ onListo }) {
  const [estado, setEstado] = useState('inactivo')
  const [segundos, setSegundos] = useState(0)
  const [error, setError] = useState(null)
  const onListoRef = useRef(onListo)
  onListoRef.current = onListo
  const r = useRef({ stream: null, recorder: null, chunks: [], inicio: 0, timer: null, descartar: false, pidiendo: false, cancelado: false })

  const soltarMicrofono = () => {
    const s = r.current
    clearInterval(s.timer)
    s.timer = null
    s.stream?.getTracks().forEach((t) => t.stop())
    s.stream = null
    s.recorder = null
  }

  const terminar = useCallback((descartar) => {
    const s = r.current
    if (s.pidiendo) {
      // Aún se está pidiendo permiso: al llegar el stream se suelta sin grabar
      s.cancelado = true
      s.pidiendo = false
      setEstado('inactivo')
      return
    }
    if (!s.recorder || s.recorder.state === 'inactive') return
    s.descartar = descartar
    s.recorder.stop()
  }, [])

  const iniciar = useCallback(async () => {
    const s = r.current
    if (s.recorder || s.pidiendo) return
    setError(null)
    if (!puedeGrabar()) {
      setError(new ErrorCaptura('soporte', 'Este navegador no puede grabar audio. Escríbeme tu mensaje o usa una nota de prueba.'))
      return
    }
    s.pidiendo = true
    s.cancelado = false
    setEstado('pidiendo')
    let stream
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, channelCount: 1 },
      })
    } catch (err) {
      s.pidiendo = false
      setEstado('inactivo')
      setError(errorDeMicrofono(err))
      return
    }
    s.pidiendo = false
    if (s.cancelado) {
      stream.getTracks().forEach((t) => t.stop())
      return
    }
    const formato = elegirFormatoAudio()
    let recorder
    try {
      recorder = new MediaRecorder(stream, formato ? { mimeType: formato, audioBitsPerSecond: 32000 } : undefined)
    } catch {
      stream.getTracks().forEach((t) => t.stop())
      setEstado('inactivo')
      setError(new ErrorCaptura('formato', 'Este navegador graba en un formato que no puedo recibir. Escríbeme tu mensaje.'))
      return
    }
    s.stream = stream
    s.recorder = recorder
    s.chunks = []
    s.descartar = false
    recorder.ondataavailable = (e) => e.data?.size && s.chunks.push(e.data)
    recorder.onstop = () => {
      const duracionS = (Date.now() - s.inicio) / 1000
      const contentType = tipoBase(recorder.mimeType || formato || s.chunks[0]?.type)
      const blob = new Blob(s.chunks, { type: contentType || 'audio/webm' })
      const descartar = s.descartar
      soltarMicrofono()
      setEstado('inactivo')
      setSegundos(0)
      if (descartar) return
      if (duracionS < AUDIO_MIN_S || blob.size === 0) {
        setError(new ErrorCaptura('corta', 'La nota quedó muy corta. Mantén presionado el micrófono mientras hablas.'))
        return
      }
      if (!audioAceptado(contentType)) {
        setError(new ErrorCaptura('formato', 'Este navegador graba en un formato que no puedo recibir. Escríbeme tu mensaje.'))
        return
      }
      if (blob.size > AUDIO_MAX_BYTES) {
        setError(new ErrorCaptura('pesada', 'La nota de voz es muy pesada. Grábala más corta.'))
        return
      }
      onListoRef.current?.({ blob, contentType, duracionS: Math.min(duracionS, AUDIO_MAX_S) })
    }
    recorder.start(250)
    s.inicio = Date.now()
    setSegundos(0)
    setEstado('grabando')
    s.timer = setInterval(() => {
      const t = (Date.now() - s.inicio) / 1000
      setSegundos(t)
      if (t >= AUDIO_MAX_S) terminar(false) // máximo 1 minuto: se envía sola
    }, 250)
  }, [terminar])

  const detener = useCallback(() => terminar(false), [terminar])
  const cancelar = useCallback(() => terminar(true), [terminar])
  const limpiarError = useCallback(() => setError(null), [])

  // Al salir del chat se suelta el micrófono
  useEffect(
    () => () => {
      const s = r.current
      s.cancelado = true
      s.descartar = true
      try {
        if (s.recorder && s.recorder.state !== 'inactive') s.recorder.stop()
      } catch {
        /* ya estaba detenido */
      }
      clearInterval(s.timer)
      s.stream?.getTracks().forEach((t) => t.stop())
    },
    [],
  )

  return { estado, segundos, error, iniciar, detener, cancelar, limpiarError }
}

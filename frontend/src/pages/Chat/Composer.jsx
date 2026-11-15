// Barra inferior: cámara · texto · micrófono (o enviar cuando hay texto).
// Micrófono: mantener presionado graba y al soltar envía; un toque corto (o Enter/Espacio con el teclado) empieza a grabar
// y otro toque envía. Mientras graba, la X cancela. Cámara: abre la cámara (móvil) o el selector de archivos (escritorio),
// achica la foto y muestra una vista previa antes de enviarla.
import { useCallback, useEffect, useId, useRef, useState } from 'react'
import { Button, Icon } from '../../components/ui/index.jsx'
import { AUDIO_MAX_S, DEMO_VOICE_NOTES, duracionTexto, prepararFoto } from './media.js'
import { useGrabadora } from './useGrabadora.js'

const MANTENER_MS = 450 // más que esto presionado = "mantener para grabar"

function VoicePicker({ id, onPick, onClose }) {
  const first = useRef(null)
  useEffect(() => {
    first.current?.focus()
    const onKey = (e) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])
  return (
    <div className="chat-picker" id={id} role="dialog" aria-label="Elegir nota de voz de prueba">
      <div className="chat-picker__head">
        <p>Notas de prueba</p>
        <button type="button" className="chat-iconbtn chat-iconbtn--plain chat-iconbtn--sm" onClick={onClose} aria-label="Cerrar">
          <Icon name="close" size={18} />
        </button>
      </div>
      {DEMO_VOICE_NOTES.map((n, i) => (
        <button key={n.id} ref={i === 0 ? first : undefined} type="button" className="chat-picker__opt" onClick={() => onPick(n)}>
          <Icon name="mic" size={18} />
          <span>“{n.texto}”</span>
          <span className="chat-picker__dur num">{n.duracion}</span>
        </button>
      ))}
    </div>
  )
}

/** Vista previa de la foto antes de enviarla */
function FotoPreview({ foto, onEnviar, onCancelar }) {
  const enviar = useRef(null)
  useEffect(() => {
    if (foto.estado === 'lista') enviar.current?.focus()
    const onKey = (e) => e.key === 'Escape' && onCancelar()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [foto.estado, onCancelar])
  return (
    <div className="chat-preview" role="dialog" aria-label="Vista previa de la foto">
      {foto.estado === 'preparando' ? (
        <p className="chat-preview__cargando" role="status">
          <span className="chat-typing__dots" aria-hidden="true">
            <i />
            <i />
            <i />
          </span>
          Preparando la foto…
        </p>
      ) : (
        <>
          <img className="chat-preview__img" src={foto.url} alt="Vista previa de la foto que vas a enviar" />
          <p className="chat-preview__nota">Revisa que se lean bien los nombres y los montos.</p>
          <div className="chat-preview__acciones">
            <Button variant="secondary" size="sm" onClick={onCancelar}>
              Cancelar
            </Button>
            <Button size="sm" icon="send" onClick={onEnviar} ref={enviar}>
              Enviar foto
            </Button>
          </div>
        </>
      )}
    </div>
  )
}

export default function Composer({ busy, onText, onVoice, onAudio, onFoto }) {
  const [text, setText] = useState('')
  const [picker, setPicker] = useState(false)
  const [foto, setFoto] = useState(null) // { estado: 'preparando' | 'lista', blob, contentType, url }
  const [aviso, setAviso] = useState(null) // error de la foto
  const [modo, setModo] = useState('mantener') // 'mantener' | 'manos_libres'
  const pickerId = useId()
  const ayudaId = useId()
  const fileRef = useRef(null)
  const press = useRef({ t: 0, empezo: false })
  const closePicker = useCallback(() => setPicker(false), [])

  const g = useGrabadora({ onListo: (nota) => onAudio(nota) })
  const grabando = g.estado !== 'inactivo'
  const hasText = text.trim().length > 0
  const error = aviso ?? g.error
  const ofrecerPrueba = g.error && ['soporte', 'permiso', 'sin_microfono', 'ocupado', 'formato'].includes(g.error.codigo)

  function submit(e) {
    e.preventDefault()
    if (!hasText || busy || grabando) return
    onText(text)
    setText('')
  }

  // ---------- Micrófono ----------
  function onPointerDown(e) {
    if (e.button !== 0 || busy) return
    e.currentTarget.setPointerCapture?.(e.pointerId)
    setAviso(null)
    press.current = { t: Date.now(), empezo: !grabando }
    if (!grabando) {
      setModo('mantener')
      g.iniciar()
    }
  }
  function onPointerUp() {
    const { t, empezo } = press.current
    if (!t) return
    press.current = { t: 0, empezo: false }
    if (empezo) {
      // Lo mantuvo presionado: al soltar se envía. Toque corto (o aún pidiendo permiso): sigue grabando hasta otro toque.
      if (Date.now() - t >= MANTENER_MS && g.estado === 'grabando') g.detener()
      else setModo('manos_libres')
    } else if (g.estado === 'grabando') {
      g.detener()
    }
  }
  function onClick(e) {
    if (e.detail !== 0 || busy) return // los clics de mouse/táctil ya los manejan los eventos de puntero
    // Teclado (Enter/Espacio): toca para empezar, toca otra vez para enviar
    if (!grabando) {
      setAviso(null)
      setModo('manos_libres')
      g.iniciar()
    } else if (g.estado === 'grabando') {
      g.detener()
    }
  }

  // ---------- Foto ----------
  async function elegirFoto(e) {
    const file = e.target.files?.[0]
    e.target.value = '' // permite elegir la misma foto otra vez
    if (!file) return
    setAviso(null)
    g.limpiarError()
    setFoto({ estado: 'preparando' })
    try {
      const { blob, contentType } = await prepararFoto(file)
      setFoto({ estado: 'lista', blob, contentType, url: URL.createObjectURL(blob) })
    } catch (err) {
      setFoto(null)
      setAviso(err)
    }
  }
  const cancelarFoto = useCallback(() => {
    setFoto((f) => {
      if (f?.url) URL.revokeObjectURL(f.url)
      return null
    })
  }, [])
  function enviarFoto() {
    if (!foto || foto.estado !== 'lista' || busy) return
    const { blob, contentType, url } = foto
    setFoto(null)
    onFoto({ blob, contentType, url })
  }

  const cerrarAviso = () => {
    setAviso(null)
    g.limpiarError()
  }

  const micLabel = g.estado === 'pidiendo' ? 'Esperando permiso del micrófono' : grabando ? 'Detener y enviar nota de voz' : 'Grabar nota de voz'
  const falta = Math.max(0, AUDIO_MAX_S - g.segundos)

  return (
    <form className="chat-composer" onSubmit={submit}>
      {picker && (
        <VoicePicker
          id={pickerId}
          onClose={closePicker}
          onPick={(n) => {
            setPicker(false)
            onVoice(n)
          }}
        />
      )}
      {foto && <FotoPreview foto={foto} onEnviar={enviarFoto} onCancelar={cancelarFoto} />}
      {error && !picker && !foto && (
        <div className="chat-aviso" role="alert">
          <Icon name="warning" size={18} className="chat-aviso__ico" />
          <p className="chat-aviso__txt">{error.message}</p>
          {ofrecerPrueba && (
            <button
              type="button"
              className="chat-aviso__accion"
              onClick={() => {
                cerrarAviso()
                setPicker(true)
              }}
            >
              Usar una nota de prueba
            </button>
          )}
          <button type="button" className="chat-iconbtn chat-iconbtn--plain chat-iconbtn--sm" onClick={cerrarAviso} aria-label="Cerrar aviso">
            <Icon name="close" size={18} />
          </button>
        </div>
      )}

      {grabando ? (
        <button type="button" className="chat-iconbtn chat-iconbtn--plain" onClick={g.cancelar} aria-label="Cancelar grabación">
          <Icon name="close" size={24} />
        </button>
      ) : (
        <>
          <button
            type="button"
            className="chat-iconbtn chat-iconbtn--plain"
            onClick={() => fileRef.current?.click()}
            disabled={busy || !!foto}
            aria-label="Mandar foto del cuaderno de fiados"
          >
            <Icon name="camera" size={24} />
          </button>
          <input ref={fileRef} type="file" accept="image/*" capture="environment" hidden onChange={elegirFoto} tabIndex={-1} />
        </>
      )}

      {grabando ? (
        <div className="chat-rec" role="status">
          <span className={g.estado === 'grabando' ? 'chat-rec__dot is-on' : 'chat-rec__dot'} aria-hidden="true" />
          <span className="chat-rec__time num" aria-hidden="true">
            {duracionTexto(g.segundos)}
          </span>
          {g.estado === 'grabando' && <span className="sr-only">Grabando nota de voz.</span>}
          {g.estado === 'grabando' && falta <= 10 ? (
            // Cuenta regresiva visible; no se anuncia cada segundo
            <span className="chat-rec__hint chat-rec__hint--fin" aria-hidden="true">
              Se envía sola en {Math.ceil(falta)} s
            </span>
          ) : (
            <span className="chat-rec__hint">
              {g.estado === 'pidiendo'
                ? 'Permite el uso del micrófono…'
                : modo === 'manos_libres'
                  ? 'Toca enviar al acabar'
                  : 'Suelta para enviar'}
            </span>
          )}
        </div>
      ) : (
        <input
          className="chat-input"
          type="text"
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Escribe un mensaje"
          aria-label="Mensaje"
          autoComplete="off"
          enterKeyHint="send"
        />
      )}

      {hasText && !grabando ? (
        <button type="submit" className="chat-iconbtn chat-iconbtn--brand" disabled={busy} aria-label="Enviar mensaje">
          <Icon name="send" size={22} />
        </button>
      ) : (
        <button
          type="button"
          className={grabando ? 'chat-iconbtn chat-iconbtn--brand chat-mic is-rec' : 'chat-iconbtn chat-iconbtn--brand chat-mic'}
          onPointerDown={onPointerDown}
          onPointerUp={onPointerUp}
          onClick={onClick}
          onContextMenu={(e) => e.preventDefault()}
          disabled={busy && !grabando}
          aria-label={micLabel}
          aria-describedby={ayudaId}
        >
          <Icon name={grabando ? 'send' : 'mic'} size={22} />
        </button>
      )}
      <span id={ayudaId} className="sr-only">
        Mantén presionado para grabar y suelta para enviar, o tócalo para empezar y otra vez para enviar. Máximo 1 minuto.
      </span>
    </form>
  )
}

// Barra inferior: cámara · texto · micrófono (o enviar cuando hay texto).
import { useCallback, useEffect, useId, useRef, useState } from 'react'
import { Icon } from '../../components/ui/index.jsx'
import { DEMO_VOICE_NOTES } from './media.js'

function VoicePicker({ id, onPick, onClose }) {
  const first = useRef(null)
  useEffect(() => {
    first.current?.focus()
    const onKey = (e) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])
  return (
    <div className="chat-picker" id={id} role="dialog" aria-label="Elegir nota de voz">
      <div className="chat-picker__head">
        <p>Notas de voz</p>
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

export default function Composer({ busy, onText, onVoice, onPhoto }) {
  const [text, setText] = useState('')
  const [picker, setPicker] = useState(false)
  const pickerId = useId()
  const closePicker = useCallback(() => setPicker(false), [])
  const hasText = text.trim().length > 0

  function submit(e) {
    e.preventDefault()
    if (!hasText || busy) return
    onText(text)
    setText('')
  }

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
      <button
        type="button"
        className="chat-iconbtn chat-iconbtn--plain"
        onClick={onPhoto}
        disabled={busy}
        aria-label="Mandar foto del cuaderno de fiados"
      >
        <Icon name="camera" size={24} />
      </button>
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
      {hasText ? (
        <button type="submit" className="chat-iconbtn chat-iconbtn--brand" disabled={busy} aria-label="Enviar mensaje">
          <Icon name="send" size={22} />
        </button>
      ) : (
        <button
          type="button"
          className="chat-iconbtn chat-iconbtn--brand"
          onClick={() => setPicker((p) => !p)}
          disabled={busy}
          aria-label="Mandar nota de voz"
          aria-expanded={picker}
          aria-controls={picker ? pickerId : undefined}
        >
          <Icon name="mic" size={22} />
        </button>
      )}
    </form>
  )
}

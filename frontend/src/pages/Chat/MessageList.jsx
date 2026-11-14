// Lista de mensajes: elige el componente según `from` + `kind` y hace auto-scroll al más nuevo.
import { useEffect, useRef } from 'react'
import { Button, Icon } from '../../components/ui/index.jsx'
import { AlertCard } from './AlertCard.jsx'
import { AssistantCard } from './AssistantCard.jsx'
import { InBubble, OutBubble, RichText, TypingBubble, Waveform } from './ChatParts.jsx'
import { CuadernoCard } from './CuadernoCard.jsx'
import { OptionsCard, WarningCard } from './PedidoCards.jsx'
import { ClarifyCard, ConfirmCard } from './RegistroCards.jsx'

function AudioBubble({ msg }) {
  return (
    <OutBubble time={msg.time} className="chat-audio">
      <span className="chat-audio__player">
        <Icon name="play" size={18} title="Nota de voz" />
        <Waveform />
        <span className="num">{msg.duracion}</span>
      </span>
      {msg.transcripcion && <p className="chat-audio__text">“{msg.transcripcion}”</p>}
    </OutBubble>
  )
}

function PhotoBubble({ msg }) {
  return (
    <OutBubble time={msg.time} className="chat-photo">
      <div className="chat-photo__img" role="img" aria-label="Foto de una página del cuaderno de fiados" />
      <p>{msg.caption}</p>
    </OutBubble>
  )
}

function Message({ msg, a }) {
  if (msg.from === 'me') {
    if (msg.kind === 'audio') return <AudioBubble msg={msg} />
    if (msg.kind === 'photo') return <PhotoBubble msg={msg} />
    return (
      <OutBubble time={msg.time}>
        <p>{msg.text}</p>
      </OutBubble>
    )
  }
  switch (msg.kind) {
    case 'confirm':
      return <ConfirmCard msg={msg} onCorrecto={() => a.correcto(msg.id)} onCorregir={() => a.corregir(msg.id)} />
    case 'clarify':
      return <ClarifyCard msg={msg} onElegir={(o) => a.elegirOpcion(msg.id, o)} />
    case 'warning':
      return (
        <WarningCard msg={msg} onVerOpciones={() => a.verOpciones(msg.id)} onRegistrar={() => a.registrarIgual(msg.id)} />
      )
    case 'options':
      return <OptionsCard msg={msg} onRegistrar={() => a.registrarIgual(msg.warningId)} />
    case 'alert':
      return <AlertCard msg={msg} onAccion={() => a.abrirAlerta(msg.id)} />
    case 'assistant':
      return <AssistantCard msg={msg} onAccion={a.accionAsistente} />
    case 'cuaderno':
      return (
        <CuadernoCard msg={msg} onGuardar={() => a.guardarCuaderno(msg.id)} onCorregir={() => a.corregirCuaderno(msg.id)} />
      )
    case 'error':
      return (
        <InBubble time={msg.time} tone="error">
          <p role="alert" className="chat-err">
            <Icon name="warning" size={18} className="chat-ico chat-ico--danger" />
            <span>{msg.text}</span>
          </p>
          {msg.retry && (
            <div className="chat-actions chat-actions--stack">
              <Button variant="secondary" size="sm" onClick={() => a.retry(msg.id)} disabled={msg.status === 'done'}>
                Intentar otra vez
              </Button>
            </div>
          )}
        </InBubble>
      )
    default:
      return (
        <InBubble time={msg.time}>
          <RichText text={msg.text} />
        </InBubble>
      )
  }
}

export default function MessageList({ messages, typing, actions }) {
  const ref = useRef(null)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    el.scrollTo({ top: el.scrollHeight, behavior: reduce ? 'auto' : 'smooth' })
  }, [messages, typing])

  return (
    <div className="chat-list" ref={ref} role="log" aria-live="polite" aria-label="Conversación con CajaClara">
      <p className="chat-date">Hoy</p>
      {messages.map((m) => (
        <Message key={m.id} msg={m} a={actions} />
      ))}
      {typing && <TypingBubble label={typing} />}
    </div>
  )
}

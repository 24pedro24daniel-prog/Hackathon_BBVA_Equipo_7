// Piezas visuales básicas del chat: filas, burbujas, texto con **negrita**, tabla clave/valor, "¿Cómo lo sé?".
import { useId, useState } from 'react'
import { Icon, MetaLine } from '../../components/ui/index.jsx'
import { confianzaLabel } from '../../lib/format.js'

const cx = (...c) => c.filter(Boolean).join(' ')

function renderBold(line) {
  return line.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
    part.startsWith('**') && part.endsWith('**') ? <strong key={i}>{part.slice(2, -2)}</strong> : part,
  )
}

/** "Listo, corregido:\n**S/ 13.00 por billetera**" → párrafos con negritas */
export function RichText({ text, className }) {
  return String(text ?? '')
    .split('\n')
    .map((line, i) => (
      <p key={i} className={className}>
        {renderBold(line)}
      </p>
    ))
}

export function Time({ children }) {
  return <span className="chat-time num">{children}</span>
}

/** Burbuja saliente (Pedro) */
export function OutBubble({ time, className, children }) {
  return (
    <div className="chat-row chat-row--me">
      <div className={cx('chat-bubble chat-bubble--out', className)}>
        {children}
        <Time>{time}</Time>
      </div>
    </div>
  )
}

/** Burbuja entrante (CajaClara). wide = tarjeta con acciones */
export function InBubble({ time, wide, tone, className, footer, children }) {
  return (
    <div className="chat-row chat-row--bot">
      <div className={cx('chat-bubble chat-bubble--in', wide && 'chat-bubble--wide', tone && `chat-bubble--${tone}`, className)}>
        {children}
        <div className="chat-foot">
          {footer ? <span className="chat-foot__note">{footer}</span> : <span />}
          <Time>{time}</Time>
        </div>
      </div>
    </div>
  )
}

/** Tabla clave/valor sobre fondo hundido */
export function KVTable({ rows, label }) {
  return (
    <dl className="chat-kv" aria-label={label}>
      {rows.map(([k, v]) => (
        <div key={k} className="chat-kv__row">
          <dt>{k}</dt>
          <dd className="num">{v}</dd>
        </div>
      ))}
    </dl>
  )
}

export function TypingBubble({ label }) {
  return (
    <div className="chat-row chat-row--bot">
      <div className="chat-bubble chat-bubble--in chat-typing" role="status">
        <span className="chat-typing__dots" aria-hidden="true">
          <i />
          <i />
          <i />
        </span>
        {label}
      </div>
    </div>
  )
}

/** Explicabilidad compacta dentro de una burbuja: fundamento, límites, confianza, cifras, modelo */
export function HowIKnow({ label = '¿Cómo lo sé?', fundamento, limites, confianza, meta, extra = [] }) {
  const [open, setOpen] = useState(false)
  const id = useId()
  const hasContent = fundamento || limites || confianza || meta || extra.length
  if (!hasContent) return null
  return (
    <div className="chat-how">
      <button
        type="button"
        className="chat-how__toggle"
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen((o) => !o)}
      >
        <Icon name="info" size={16} />
        {label}
        <Icon name="chevronDown" size={16} className="chat-how__chev" />
      </button>
      {open && (
        <dl className="chat-how__body" id={id}>
          {fundamento && (
            <div>
              <dt>De dónde sale</dt>
              <dd>{fundamento}</dd>
            </div>
          )}
          {extra.map(([k, v]) => (
            <div key={k}>
              <dt>{k}</dt>
              <dd>{v}</dd>
            </div>
          ))}
          {limites && (
            <div>
              <dt>Lo que no sabe</dt>
              <dd>{limites}</dd>
            </div>
          )}
          {confianza !== undefined && confianza !== null && (
            <div>
              <dt>Qué tan seguro es</dt>
              <dd>{confianzaLabel(confianza)}</dd>
            </div>
          )}
          {meta && <MetaLine meta={meta} />}
        </dl>
      )}
    </div>
  )
}

const BARS = [5, 9, 14, 8, 17, 11, 6, 13, 18, 10, 15, 7, 12, 16, 9, 5, 11, 14, 8, 6]

/** Forma de onda decorativa de la nota de voz */
export function Waveform() {
  return (
    <svg className="chat-wave" viewBox={`0 0 ${BARS.length * 4} 20`} width={BARS.length * 4} height="20" aria-hidden="true">
      {BARS.map((h, i) => (
        <rect key={i} x={i * 4} y={(20 - h) / 2} width="2" height={h} rx="1" fill="currentColor" />
      ))}
    </svg>
  )
}

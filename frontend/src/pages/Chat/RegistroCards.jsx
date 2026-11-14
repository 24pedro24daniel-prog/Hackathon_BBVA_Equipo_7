// F1: "Anoté esto, ¿está bien?" y la pregunta aclaratoria.
import { Badge, Button } from '../../components/ui/index.jsx'
import { soles } from '../../lib/format.js'
import { InBubble, KVTable, RichText } from './ChatParts.jsx'
import { filasMovimiento, notaDuda, resumenEntendido } from './chatText.js'

export function ConfirmCard({ msg, onCorrecto, onCorregir }) {
  const { res, status, dudoso, time } = msg
  const mov = res.movimiento_propuesto
  const item = mov.items?.[0]
  const locked = status === 'done' || status === 'saving'
  return (
    <InBubble wide time={time}>
      <h2 className="chat-card__title">
        Anoté esto, ¿está bien?
        {dudoso && <Badge tone="warning">Revisa</Badge>}
      </h2>
      <KVTable rows={filasMovimiento(mov)} label="Lo que anoté" />
      {res.origen_monto === 'catalogo' && item?.precio_unitario && (
        <p className="chat-note">Usé el precio de tu lista: {soles(item.precio_unitario, { cents: true })} cada una.</p>
      )}
      {res.origen_monto === 'estimado' && <p className="chat-note">El monto es un estimado; corrígelo si no es así.</p>}
      <div className="chat-actions">
        <Button onClick={onCorrecto} disabled={locked}>
          ✅ Correcto
        </Button>
        <Button variant="secondary" onClick={onCorregir} disabled={locked || status === 'editing'}>
          ✏️ Corregir
        </Button>
      </div>
      {status === 'done' && <p className="chat-status">Guardado</p>}
    </InBubble>
  )
}

export function ClarifyCard({ msg, onElegir }) {
  const { res, status, elegido, time } = msg
  const opciones = res.opciones_aclaracion || []
  return (
    <InBubble wide time={time} footer={notaDuda(res.campos_faltantes)}>
      <RichText text={resumenEntendido(res.movimiento_propuesto)} />
      <p className="chat-card__q">{res.pregunta_aclaratoria}</p>
      {opciones.length > 0 && (
        <div className="chat-actions">
          {opciones.map((o) => (
            <Button
              key={o.valor}
              variant="secondary"
              onClick={() => onElegir(o)}
              disabled={status !== 'pending'}
              aria-pressed={elegido === o.valor}
              className={elegido === o.valor ? 'chat-opt--chosen' : undefined}
            >
              {o.texto}
            </Button>
          ))}
        </div>
      )}
    </InBubble>
  )
}

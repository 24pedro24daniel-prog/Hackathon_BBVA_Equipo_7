// F1: "Anoté esto, ¿está bien?" y la pregunta aclaratoria.
import { Button, Icon } from '../../components/ui/index.jsx'
import { soles } from '../../lib/format.js'
import { CardTitle, InBubble, KVTable, RichText, SavedLine, StatusText } from './ChatParts.jsx'
import { filasMovimiento, notaDuda, resumenEntendido } from './chatText.js'

export function ConfirmCard({ msg, onCorrecto, onCorregir }) {
  const { res, status, dudoso, time } = msg
  const mov = res.movimiento_propuesto
  const item = mov.items?.[0]
  const locked = status === 'done' || status === 'saving'
  return (
    <InBubble wide time={time}>
      <div className="chat-card__head">
        <CardTitle>Anoté esto, ¿está bien?</CardTitle>
        {dudoso && <StatusText tone="warning">Revisa antes de guardar</StatusText>}
      </div>
      <KVTable rows={filasMovimiento(mov)} label="Lo que anoté" />
      {res.origen_monto === 'catalogo' && item?.precio_unitario && (
        <p className="chat-note">Usé el precio de tu lista: {soles(item.precio_unitario, { cents: true })} cada una.</p>
      )}
      {res.origen_monto === 'estimado' && <p className="chat-note">El monto es un estimado; corrígelo si no es así.</p>}
      <div className="chat-actions">
        <Button icon="check" onClick={onCorrecto} disabled={locked}>
          Correcto
        </Button>
        <Button variant="secondary" onClick={onCorregir} disabled={locked || status === 'editing'}>
          Corregir
        </Button>
      </div>
      {status === 'done' && <SavedLine />}
    </InBubble>
  )
}

/** Pregunta en la burbuja; las respuestas van debajo, a la derecha, como píldoras (lo que Pedro diría). */
export function ClarifyCard({ msg, onElegir }) {
  const { res, status, elegido, time } = msg
  const opciones = res.opciones_aclaracion || []
  return (
    <>
      <InBubble wide time={time} footer={notaDuda(res.campos_faltantes)}>
        <RichText text={resumenEntendido(res.movimiento_propuesto)} />
        <p className="chat-card__q">{res.pregunta_aclaratoria}</p>
      </InBubble>
      {opciones.length > 0 && (
        <div className="chat-quick" role="group" aria-label={res.pregunta_aclaratoria || 'Respuestas sugeridas'}>
          {opciones.map((o) => (
            <button
              key={o.valor}
              type="button"
              className="chat-chip"
              onClick={() => onElegir(o)}
              disabled={status !== 'pending'}
              aria-pressed={elegido === o.valor}
            >
              {elegido === o.valor && <Icon name="check" size={18} />}
              {o.texto}
            </button>
          ))}
        </div>
      )}
    </>
  )
}

// F6: alerta proactiva como primer mensaje del día.
import { Button } from '../../components/ui/index.jsx'
import { probabilidadTexto, soles } from '../../lib/format.js'
import { CardTitle, HowIKnow, InBubble, RichText } from './ChatParts.jsx'
import { boldMonto } from './chatText.js'

export function AlertCard({ msg, onAccion }) {
  const { alerta, total, time } = msg
  const base = (alerta.insight || alerta.titulo || '').replace(/\.\s*$/, '')
  const prob = probabilidadTexto(alerta.probabilidad)
  const causas =
    alerta.resumen_causas ||
    (alerta.causas || []).map((c) => `${c.descripcion.toLowerCase()} (${soles(c.monto)})`).join(', ')
  return (
    <InBubble wide time={time} className="chat-alert" footer={total > 0 ? `Alerta 1 de ${total} hoy` : null}>
      <CardTitle icon="warning" tone="danger">
        {alerta.titulo_corto || alerta.titulo}
      </CardTitle>
      <RichText text={`${boldMonto(base, alerta.monto)}.${prob ? ` ${prob}.` : ''}`} />
      {causas && <p className="chat-why">Por qué: {causas}</p>}
      {alerta.accion && (
        <div className="chat-actions chat-actions--stack">
          <Button block onClick={onAccion}>
            {alerta.accion.texto_boton || 'Ver qué puedo hacer'}
          </Button>
        </div>
      )}
      <HowIKnow
        fundamento={alerta.microexplicacion}
        extra={(alerta.causas || []).map((c) => [c.descripcion, soles(c.monto)])}
        meta={alerta.meta}
      />
    </InBubble>
  )
}

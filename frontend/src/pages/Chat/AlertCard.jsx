// F6: alerta proactiva como primer mensaje del día.
import { Button } from '../../components/ui/index.jsx'
import { probabilidadTexto, soles } from '../../lib/format.js'
import { destinoAlerta, estiloAlerta } from '../../lib/alertas.js'
import { CardTitle, HowIKnow, InBubble, RichText } from './ChatParts.jsx'
import { boldMonto } from './chatText.js'

export function AlertCard({ msg, onAccion }) {
  const { alerta, total, time } = msg
  const base = (alerta.insight || alerta.titulo || '').replace(/\.\s*$/, '')
  const prob = probabilidadTexto(alerta.probabilidad)
  const lista = (alerta.causas || []).filter((c) => c?.descripcion)
  const causas =
    alerta.resumen_causas || lista.map((c) => `${c.descripcion.toLowerCase()} (${soles(c.monto)})`).join(', ')
  const { icon, tone } = estiloAlerta(alerta)
  const destino = destinoAlerta(alerta)
  return (
    <InBubble wide time={time} className="chat-alert" footer={total > 0 ? `Alerta 1 de ${total} hoy` : null}>
      <CardTitle icon={icon} tone={tone}>
        {alerta.titulo_corto || alerta.titulo}
      </CardTitle>
      <RichText text={`${boldMonto(base, alerta.monto)}.${prob ? ` ${prob}.` : ''}`} />
      {causas && <p className="chat-why">Por qué: {causas}</p>}
      {destino && (
        <div className="chat-actions chat-actions--stack">
          <Button block onClick={() => onAccion(alerta)}>
            {destino.texto}
          </Button>
        </div>
      )}
      <HowIKnow
        fundamento={alerta.microexplicacion}
        extra={lista.map((c) => [c.descripcion, soles(c.monto)])}
        meta={alerta.meta}
      />
    </InBubble>
  )
}

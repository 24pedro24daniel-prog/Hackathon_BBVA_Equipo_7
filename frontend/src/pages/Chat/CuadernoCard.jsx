// Foto del cuaderno de fiados → fiados propuestos para revisar.
import { Badge, Button } from '../../components/ui/index.jsx'
import { ddmm, soles } from '../../lib/format.js'
import { HowIKnow, InBubble, RichText } from './ChatParts.jsx'

export function CuadernoCard({ msg, onGuardar, onCorregir }) {
  const { res, montos, status, time } = msg
  const fiados = res.fiados_propuestos
  const n = fiados.length
  const ilegibles = res.lineas_no_legibles || 0
  const dudas = fiados.filter((f) => f.alternativas_monto?.length > 1)
  const locked = status === 'done' || status === 'saving'
  return (
    <InBubble wide time={time}>
      <RichText text={`Leí **${n} ${n === 1 ? 'fiado' : 'fiados'}** en tu foto:`} />
      <ul className="chat-fiados">
        {fiados.map((f, i) => (
          <li key={`${f.cliente}-${i}`} className="chat-fiados__row">
            <div className="chat-fiados__main">
              <span className="chat-fiados__name">
                {f.cliente}
                {f.confianza < 0.75 && <Badge tone="warning">Revisa</Badge>}
              </span>
              <strong className="num">{soles(montos[i])}</strong>
            </div>
            <p className="chat-fiados__sub num">
              {f.fecha ? `${ddmm(f.fecha)} · ` : ''}
              {f.detalle}
            </p>
          </li>
        ))}
      </ul>
      {(ilegibles > 0 || dudas.length > 0) && (
        <p className="chat-note chat-note--body">
          {ilegibles > 0 && `Hay ${ilegibles} ${ilegibles === 1 ? 'línea' : 'líneas'} que no pude leer. `}
          {dudas
            .map((f) => `${f.cliente}: ¿son ${f.alternativas_monto.map((m) => soles(m)).join(' o ')}?`)
            .join(' ')}
        </p>
      )}
      <div className="chat-actions">
        <Button onClick={onGuardar} disabled={locked}>
          Sí, guardar
        </Button>
        <Button variant="secondary" onClick={onCorregir} disabled={locked || status === 'editing'}>
          No, corregir
        </Button>
      </div>
      {status === 'done' && <p className="chat-status">Guardado</p>}
      <HowIKnow
        fundamento="Leí tu letra con un modelo de lectura de manuscritos; las líneas marcadas «Revisa» son las que leí con menos seguridad."
        meta={res.meta}
      />
    </InBubble>
  )
}

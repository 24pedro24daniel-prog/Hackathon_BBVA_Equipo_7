// "Probar qué hacer" (30 días): el problema en una línea, 2–3 pasos numerados con lo que recupera cada uno y acciones.
import { Button, Money } from '../../components/ui/index.jsx'
import { CardTitle, InBubble, RichText } from './ChatParts.jsx'

const ICON = { danger: 'warning', warning: 'warning', ok: 'check' }

export function PlanCard({ msg, onAccion }) {
  const { plan, time, usadas = [] } = msg
  return (
    <InBubble wide time={time} footer="Orientación educativa · tú decides">
      <CardTitle icon={ICON[plan.tone]} tone={plan.tone}>
        {plan.titulo}
      </CardTitle>
      <RichText text={plan.problema} />
      {plan.pasos.length > 0 && (
        <>
          {plan.pasosTitulo && <p className="chat-card__q">{plan.pasosTitulo}</p>}
          <ol className="chat-plan">
            {plan.pasos.map((p, i) => (
              <li key={i} className="chat-plan__step">
                <span className="chat-plan__n num" aria-hidden="true">
                  {i + 1}
                </span>
                <span className="chat-plan__text">{p.texto}</span>
                {plan.tone !== 'ok' && p.monto > 0 && (
                  <span className="chat-plan__amt">
                    <Money value={p.monto} sign tone="pos" />
                  </span>
                )}
              </li>
            ))}
          </ol>
        </>
      )}
      {plan.resultado && <RichText text={plan.resultado} />}
      {plan.acciones.length > 0 && (
        <div className="chat-actions chat-actions--stack">
          {plan.acciones.map((a, i) => (
            <Button
              key={a.tipo}
              block
              variant={i === 0 ? 'primary' : 'ghost'}
              disabled={usadas.includes(a.tipo)}
              onClick={() => onAccion(a)}
            >
              {a.texto}
            </Button>
          ))}
        </div>
      )}
    </InBubble>
  )
}

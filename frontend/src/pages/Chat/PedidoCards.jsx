// Pedido a crédito: advertencia "Antes de confirmar" (POST /pedidos/chequeo) y lista de opciones.
import { Link } from 'react-router-dom'
import { Button, Icon } from '../../components/ui/index.jsx'
import { confianzaLabel, ddmm, soles } from '../../lib/format.js'
import { HowIKnow, InBubble, RichText, SavedLine } from './ChatParts.jsx'
import { sugerenciaTexto } from './chatText.js'

export function WarningCard({ msg, onVerOpciones, onRegistrar }) {
  const { chequeo, res, correcciones, status, opcionesVistas, time } = msg
  const mov = res.movimiento_propuesto
  const fecha = ddmm(correcciones.fecha_vencimiento)
  const saldo = chequeo.saldo_proyectado_al_vencimiento
  const texto =
    saldo < 0
      ? `Si pides ${soles(mov.monto)}, **el ${fecha} te faltarían ${soles(-saldo)}** para pagarlo.`
      : `Si pides ${soles(mov.monto)}, **el ${fecha} te quedarían solo ${soles(saldo)}** después de pagarlo.`
  const locked = status !== 'pending'
  return (
    <InBubble
      wide
      time={time}
      footer={`${confianzaLabel(chequeo.confianza)} · basado en tus últimos 3 meses`}
    >
      <h2 className="chat-card__title chat-card__title--danger">
        <Icon name="warning" size={20} />
        Antes de confirmar
      </h2>
      <RichText text={texto} />
      {chequeo.fundamento && <p className="chat-why">Por qué: {lowerFirst(chequeo.fundamento)}</p>}
      <div className="chat-actions chat-actions--stack">
        <Button block onClick={onVerOpciones} disabled={locked || opcionesVistas}>
          Ver opciones
        </Button>
        <Button variant="ghost" block onClick={onRegistrar} disabled={locked}>
          Registrar igual
        </Button>
      </div>
      {status === 'done' && <SavedLine>Pedido registrado</SavedLine>}
      <HowIKnow
        fundamento={chequeo.fundamento}
        limites={chequeo.limites}
        confianza={chequeo.confianza}
        meta={chequeo.meta}
        extra={[
          ['Lo que sueles vender en ese tiempo', soles(chequeo.venta_esperada_periodo)],
          ...(chequeo.exceso_vs_ventas > 0 ? [['Pedido por encima de tus ventas', soles(chequeo.exceso_vs_ventas)]] : []),
        ]}
      />
    </InBubble>
  )
}

export function OptionsCard({ msg, onRegistrar }) {
  const { chequeo, fecha, status, time } = msg
  const sugs = chequeo.sugerencias || []
  const ordenadas = [...sugs].sort((a, b) => b.saldo_resultante - a.saldo_resultante)
  const alcanzan = ordenadas.filter((s) => s.saldo_resultante >= 0)
  const noAlcanzan = ordenadas.filter((s) => s.saldo_resultante < 0)
  return (
    <InBubble wide time={time} footer="Tú decides · nada se registra sin tu confirmación">
      <p>
        {alcanzan.length
          ? `Estas opciones te dejan pagar el ${ddmm(fecha)}:`
          : `Con estas opciones, el ${ddmm(fecha)} quedarías así:`}
      </p>
      <ul className="chat-opts">
        {(alcanzan.length ? alcanzan : noAlcanzan).map((s) => (
          <li key={s.accion} className="chat-opts__row">
            <span>{sugerenciaTexto(s, sugs)}</span>
            <strong className={s.saldo_resultante < 0 ? 'chat-neg num' : 'chat-pos num'}>
              {s.saldo_resultante < 0 ? `te faltan ${soles(-s.saldo_resultante)}` : `te quedan ${soles(s.saldo_resultante)}`}
            </strong>
          </li>
        ))}
      </ul>
      {alcanzan.length > 0 &&
        noAlcanzan.map((s) => (
          <p key={s.accion} className="chat-note">
            {sugerenciaTexto(s, sugs)} solo: aún te faltarían {soles(-s.saldo_resultante)}.
          </p>
        ))}
      <div className="chat-actions chat-actions--stack">
        <Link to="/simulador" className="cc-btn cc-btn--primary cc-btn--block">
          Probar en el simulador
        </Link>
        <Button variant="ghost" block onClick={onRegistrar} disabled={status !== 'pending'}>
          Registrar igual
        </Button>
      </div>
    </InBubble>
  )
}

function lowerFirst(s = '') {
  return s.charAt(0).toLowerCase() + s.slice(1)
}

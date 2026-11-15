import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../../api/index.js'
import { useApi } from '../../api/useApi.js'
import { ddmm, soles } from '../../lib/format.js'
import { useSearchParams } from 'react-router-dom'
import { Card, ErrorState, Icon, LoadingBlock, MetaLine, Money, PageHeader, TraceInfo } from '../../components/ui/index.jsx'
import './Simulador.css'

/** "2026-11-30" + 15 → "2026-12-15" */
function addDays(iso, n) {
  const d = new Date(`${iso}T00:00:00Z`)
  d.setUTCDate(d.getUTCDate() + n)
  return d.toISOString().slice(0, 10)
}

function joinNombres(nombres) {
  if (nombres.length <= 1) return nombres.join('')
  return `${nombres.slice(0, -1).join(', ')} y ${nombres[nombres.length - 1]}`
}

/**
 * Todo lo que la pantalla necesita, sacado del backend: pedido pendiente, chequeo, fiados, mínimo y resultado inicial.
 * `pedidoId` (?pedido_id=, p. ej. desde una alerta): el pedido a simular; si no existe, el del día crítico.
 */
async function cargarEscenario(pedidoId) {
  const [forecast, pedidos, fiados] = await Promise.all([api.getForecast(30), api.getPedidos(), api.getFiados('pendiente')])
  const items = pedidos.items || []
  const pedido =
    items.find((p) => p.pedido_id === pedidoId) ||
    items.find((p) => p.pedido_id === forecast.dia_critico?.obligacion_asociada?.id) ||
    items[0]
  if (!pedido) return null
  // Sin acciones, /simular da el punto de partida antes de mover opciones.
  const [chequeo, inicial] = await Promise.all([
    api.chequearPedido({ proveedor: pedido.proveedor, monto: pedido.monto, fecha_vencimiento: pedido.fecha_vencimiento }),
    api.simular([]),
  ])
  const reducir = chequeo.sugerencias?.find((s) => s.accion === 'reducir_pedido')?.monto_sugerido
  const opciones = [
    { monto: pedido.monto, texto: 'Lo que pediste' },
    { monto: chequeo.venta_esperada_periodo, texto: 'Lo que vendes en 2 semanas' },
    { monto: reducir, texto: 'Solo lo que más se vende' },
  ].filter((o, i, all) => o.monto > 0 && o.monto <= pedido.monto && all.findIndex((x) => x.monto === o.monto) === i)
  return {
    pedido,
    opciones,
    minimo: forecast.minimo_operativo,
    fechasPartes: [pedido.fecha_vencimiento, addDays(pedido.fecha_vencimiento, 15)],
    fechaCobro: addDays(forecast.fecha_corte, 6),
    fiados: fiados.items || [],
    totalFiados: fiados.total_pendiente,
    inicial,
  }
}

function buildAcciones(esc, { monto, partes, cobrar }) {
  const pedido_id = esc.pedido.pedido_id
  const acciones = []
  if (monto !== esc.pedido.monto) acciones.push({ tipo: 'reducir_pedido', pedido_id, nuevo_monto: monto })
  if (partes) acciones.push({ tipo: 'pagar_en_partes', pedido_id, partes: 2, fechas: esc.fechasPartes })
  if (cobrar && esc.fiados.length) {
    acciones.push({ tipo: 'cobrar_fiados', fiado_ids: esc.fiados.map((f) => f.fiado_id), fecha: esc.fechaCobro })
  }
  return acciones
}

export default function Simulador() {
  const [params] = useSearchParams()
  const pedidoId = params.get('pedido_id')
  const { data: esc, error, loading, reload } = useApi(() => cargarEscenario(pedidoId), [pedidoId])

  if (loading && !esc)
    return (
      <Shell>
        <LoadingBlock heights={[220, 140, 180]} />
      </Shell>
    )
  if (error)
    return (
      <Shell>
        <ErrorState error={error} onRetry={reload} />
      </Shell>
    )
  if (!esc)
    return (
      <Shell>
        <Card>
          <h2 className="cc-card__title">No tienes pedidos por pagar</h2>
          <p className="cc-muted">Cuando anotes un pedido a crédito, aquí podrás probar qué hacer antes de pagarlo.</p>
        </Card>
      </Shell>
    )
  return <SimuladorEscenario key={esc.pedido.pedido_id} esc={esc} />
}

function Shell({ sub, children }) {
  return (
    <div className="sim-page">
      <PageHeader back sub={sub} title="¿Qué puedo hacer?" />
      <div className="sim-body">{children}</div>
    </div>
  )
}

function SimuladorEscenario({ esc }) {
  const { pedido, opciones, minimo, fiados: items, totalFiados } = esc
  const [monto, setMonto] = useState(pedido.monto)
  const [partes, setPartes] = useState(false)
  const [cobrar, setCobrar] = useState(false)
  const [sim, setSim] = useState({
    data: esc.inicial,
    error: null,
    loading: false,
  })
  const callId = useRef(0)

  const run = useCallback(
    (acciones) => {
      const id = ++callId.current
      setSim((s) => ({ ...s, loading: true, error: null }))
      api.simular(acciones).then(
        (data) => id === callId.current && setSim({ data, error: null, loading: false }),
        (error) => id === callId.current && setSim((s) => ({ data: s.data, error, loading: false })),
      )
    },
    [],
  )

  useEffect(() => {
    const t = setTimeout(() => run(buildAcciones(esc, { monto, partes, cobrar })), 180)
    return () => clearTimeout(t)
  }, [esc, monto, partes, cobrar, run])

  const retry = () => run(buildAcciones(esc, { monto, partes, cobrar }))

  return (
    <Shell sub={`Antes del ${ddmm(pedido.fecha_vencimiento)}`}>
      <div className="sim-options">
        <Card flush as="div">
          <fieldset className="sim-group">
            <legend className="cc-card__title sim-legend">¿Cuánto le pides a {pedido.proveedor}?</legend>
            <div className="sim-list">
              {opciones.map((o) => (
                <label key={o.monto} className="sim-row">
                  <input
                    type="radio"
                    name="sim-monto"
                    className="sim-input"
                    value={o.monto}
                    checked={monto === o.monto}
                    onChange={() => setMonto(o.monto)}
                  />
                  <span className="sim-row__text">
                    <Money value={o.monto} size="md" className="sim-row__title" />
                    <span className="sim-row__sub">{o.texto}</span>
                  </span>
                  <span className="sim-radio" aria-hidden="true" />
                </label>
              ))}
            </div>
          </fieldset>
        </Card>

        <Card flush as="div">
          <fieldset className="sim-group">
            <legend className="cc-card__title sim-legend">También puedes</legend>
            <div className="sim-list">
              <label className="sim-row">
                <span className="sim-row__text">
                  <span className="sim-row__title">Pagar en 2 partes</span>
                  <span className="sim-row__sub">
                    Mitad el {ddmm(esc.fechasPartes[0])} y mitad el {ddmm(esc.fechasPartes[1])} (pídelo a {pedido.proveedor})
                  </span>
                </span>
                <input
                  type="checkbox"
                  role="switch"
                  className="sim-input"
                  checked={partes}
                  onChange={(e) => setPartes(e.target.checked)}
                />
                <span className="sim-switch" aria-hidden="true" />
              </label>

              {items.length > 0 && (
                <label className="sim-row">
                  <span className="sim-row__text">
                    <span className="sim-row__title">Cobrar los fiados esta semana</span>
                    <span className="sim-row__sub">
                      {joinNombres(items.map((f) => f.cliente))} · <span className="num">{soles(totalFiados)}</span>
                    </span>
                  </span>
                  <input
                    type="checkbox"
                    role="switch"
                    className="sim-input"
                    checked={cobrar}
                    onChange={(e) => setCobrar(e.target.checked)}
                  />
                  <span className="sim-switch" aria-hidden="true" />
                </label>
              )}
            </div>
          </fieldset>
        </Card>
      </div>

      <div className="sim-aside">
        <div aria-live="polite" aria-busy={sim.loading}>
          <Resultado r={sim.data} pending={sim.loading} minimo={minimo} proveedor={pedido.proveedor} />
          {sim.error && (
            <p className="cc-small sim-stale" role="alert">
              No pude actualizar el cálculo.{' '}
              <button type="button" className="sim-link" onClick={retry}>
                Intentar otra vez
              </button>
            </p>
          )}
        </div>
        <Detalle r={sim.data} />

        <div className="sim-foot">
          <p>Simulación con tus ventas y gastos recientes. Tú decides; nada se ejecuta solo.</p>
          {sim.data.meta && <MetaLine meta={sim.data.meta} />}
        </div>
      </div>
    </Shell>
  )
}

/** Lo que el backend avisa del cálculo: notas visibles (p. ej. un pago que cae fuera de la proyección) y, plegado, de dónde sale. */
function Detalle({ r }) {
  const notas = (r.notas || []).filter(Boolean)
  const extra = r.ventana_hasta ? [['Hasta qué día mira', ddmm(r.ventana_hasta)]] : []
  const hayTrace = r.fundamento || r.limites || extra.length > 0
  if (!notas.length && !hayTrace) return null
  return (
    <>
      {notas.length > 0 && (
        <ul className="sim-notas">
          {notas.map((n, i) => (
            <li key={i}>{n}</li>
          ))}
        </ul>
      )}
      {hayTrace && <TraceInfo fundamento={r.fundamento} limites={r.limites} confianza={r.confianza} extra={extra} />}
    </>
  )
}

const ESTADOS = {
  no_te_alcanza: {
    tone: 'danger',
    icon: 'warning',
    money: { tone: 'neg' },
    titulo: 'No te alcanza',
  },
  justo: {
    tone: 'warning',
    icon: 'warning',
    money: { className: 'sim-money--warning' },
    titulo: 'Justo',
  },
  te_alcanza: {
    tone: 'ok',
    icon: 'check',
    money: { tone: 'pos' },
    titulo: 'Te alcanza',
  },
}

function Resultado({ r, pending, minimo, proveedor }) {
  const saldo = r.con_acciones.saldo_minimo
  const fecha = ddmm(r.con_acciones.fecha)
  const estado = r.con_acciones.estado_caja
  const mejora = r.mejora ?? 0
  const e = ESTADOS[estado] || ESTADOS.justo

  const explicacion =
    estado === 'no_te_alcanza'
      ? `Todavía te faltaría plata para pagar a ${proveedor}. Prueba combinar opciones.`
      : estado === 'justo'
        ? `Te alcanza para pagar, pero quedas debajo de tu mínimo de ${soles(minimo)}.`
        : `Pasas tu mínimo de ${soles(minimo)} para el día a día.`

  return (
    <Card className={'sim-result' + (pending ? ' is-pending' : '')} aria-labelledby="sim-result-label">
      <p id="sim-result-label" className="sim-result__label">
        Tu caja el {fecha} después de pagar
      </p>
      <Money
        value={saldo}
        size="hero"
        tone={e.money.tone}
        className={['sim-result__amount', e.money.className].filter(Boolean).join(' ')}
      />
      <p className={`sim-result__status sim-result__status--${e.tone}`}>
        <Icon name={e.icon} size={20} />
        {e.titulo}
      </p>
      <p className="sim-result__main">{explicacion}</p>
      {estado !== 'no_te_alcanza' && mejora > 0 && (
        <p className="sim-result__note num">{soles(mejora, { sign: true })} mejor que no hacer nada.</p>
      )}
    </Card>
  )
}

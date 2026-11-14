import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../../api/index.js'
import { useApi } from '../../api/useApi.js'
import { ddmm, soles } from '../../lib/format.js'
import { Card, ErrorState, Icon, LoadingBlock, MetaLine, PageHeader, Skeleton } from '../../components/ui/index.jsx'
import './Simulador.css'

// Escenario del mockup: pedido a Distribuidora Andina que vence el 30/11.
const PEDIDO_ID = 'PED-0012'
const PEDIDO_MONTO = 2400
const FECHAS_PARTES = ['2026-11-30', '2026-12-15']
const FECHA_COBRO = '2026-11-20'
const MINIMO = 800

const OPCIONES = [
  { monto: 2400, texto: 'Lo que pediste' },
  { monto: 2000, texto: 'Lo que vendes en 2 semanas' },
  { monto: 1800, texto: 'Solo lo que más se vende' },
]

function joinNombres(nombres) {
  if (nombres.length <= 1) return nombres.join('')
  return `${nombres.slice(0, -1).join(', ')} y ${nombres[nombres.length - 1]}`
}

function buildAcciones({ monto, partes, cobrar, fiadoIds }) {
  const acciones = []
  if (monto !== PEDIDO_MONTO) acciones.push({ tipo: 'reducir_pedido', pedido_id: PEDIDO_ID, nuevo_monto: monto })
  if (partes) acciones.push({ tipo: 'pagar_en_partes', pedido_id: PEDIDO_ID, partes: 2, fechas: FECHAS_PARTES })
  if (cobrar && fiadoIds.length) acciones.push({ tipo: 'cobrar_fiados', fiado_ids: fiadoIds, fecha: FECHA_COBRO })
  return acciones
}

export default function Simulador() {
  const [monto, setMonto] = useState(PEDIDO_MONTO)
  const [partes, setPartes] = useState(false)
  const [cobrar, setCobrar] = useState(false)

  const fiados = useApi(() => api.getFiados('pendiente'), [])
  const items = fiados.data?.items || []
  const fiadoIds = items.map((f) => f.fiado_id)
  const fiadoKey = fiadoIds.join(',')
  const totalFiados = fiados.data?.total_pendiente ?? items.reduce((s, f) => s + f.monto, 0)

  const [sim, setSim] = useState({ data: null, error: null, loading: true })
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
    const ids = fiadoKey ? fiadoKey.split(',') : []
    const t = setTimeout(() => run(buildAcciones({ monto, partes, cobrar, fiadoIds: ids })), 180)
    return () => clearTimeout(t)
  }, [monto, partes, cobrar, fiadoKey, run])

  const retry = () => run(buildAcciones({ monto, partes, cobrar, fiadoIds }))

  return (
    <div className="sim-page">
      <PageHeader back kicker="Antes del 30/11" title="¿Qué puedo hacer?" />
      <div className="sim-body">
        <fieldset className="sim-group">
          <legend className="sim-legend">Tu pedido a Andina · ¿cuánto pedir?</legend>
          {OPCIONES.map((o) => (
            <label key={o.monto} className="sim-option">
              <input
                type="radio"
                name="sim-monto"
                className="sim-input"
                value={o.monto}
                checked={monto === o.monto}
                onChange={() => setMonto(o.monto)}
              />
              <span className="sim-option__text">
                <span className="sim-option__amount display num">{soles(o.monto)}</span>
                <span className="sim-option__sub">{o.texto}</span>
              </span>
              {monto === o.monto && <span className="sim-option__chosen">Elegido</span>}
            </label>
          ))}
        </fieldset>

        <fieldset className="sim-group">
          <legend className="sr-only">Otras cosas que puedes hacer</legend>
          <label className="sim-option sim-option--check">
            <input type="checkbox" className="sim-input" checked={partes} onChange={(e) => setPartes(e.target.checked)} />
            <span className="sim-box" aria-hidden="true">
              <Icon name="check" size={18} />
            </span>
            <span className="sim-option__text">
              <span className="sim-option__title">Pagar en 2 partes</span>
              <span className="sim-option__sub">Mitad el 30/11 y mitad el 15/12 (pídelo a Andina)</span>
            </span>
          </label>

          {fiados.loading ? (
            <Skeleton height={72} />
          ) : fiados.error ? (
            <p className="cc-small cc-muted">
              No pude traer tus fiados.{' '}
              <button type="button" className="sim-link" onClick={fiados.reload}>
                Intentar otra vez
              </button>
            </p>
          ) : items.length ? (
            <label className="sim-option sim-option--check">
              <input type="checkbox" className="sim-input" checked={cobrar} onChange={(e) => setCobrar(e.target.checked)} />
              <span className="sim-box" aria-hidden="true">
                <Icon name="check" size={18} />
              </span>
              <span className="sim-option__text">
                <span className="sim-option__title">Cobrar los fiados esta semana</span>
                <span className="sim-option__sub">
                  {joinNombres(items.map((f) => f.cliente))} · <span className="num">{soles(totalFiados)}</span>
                </span>
              </span>
            </label>
          ) : null}
        </fieldset>

        <div aria-live="polite" aria-busy={sim.loading}>
          {sim.error && !sim.data ? (
            <ErrorState error={sim.error} onRetry={retry} />
          ) : !sim.data ? (
            <LoadingBlock heights={[180]} />
          ) : (
            <>
              <Resultado r={sim.data} pending={sim.loading} />
              {sim.error && (
                <p className="cc-small sim-stale" role="alert">
                  No pude actualizar el cálculo.{' '}
                  <button type="button" className="sim-link" onClick={retry}>
                    Intentar otra vez
                  </button>
                </p>
              )}
            </>
          )}
        </div>

        <div className="sim-foot">
          <p>Simulación con tus ventas de los últimos 3 meses. Tú decides; nada se ejecuta solo.</p>
          {sim.data?.meta && <MetaLine meta={sim.data.meta} />}
        </div>
      </div>
    </div>
  )
}

function Resultado({ r, pending }) {
  const saldo = r.con_acciones?.saldo_minimo
  const fecha = ddmm(r.con_acciones?.fecha || '2026-11-30')
  const estado = r.con_acciones?.estado_caja || (saldo < 0 ? 'no_te_alcanza' : saldo < MINIMO ? 'justo' : 'te_alcanza')
  const mejora = r.mejora ?? 0

  const cls = 'sim-result sim-result--' + estado + (pending ? ' is-pending' : '')

  if (estado === 'no_te_alcanza')
    return (
      <section className={cls}>
        <p className="sim-result__kicker">No te alcanza</p>
        <p>Tu caja el {fecha} después de pagar:</p>
        <p className="sim-result__amount display num">{soles(saldo)}</p>
        <p className="sim-result__main">Todavía te faltaría plata para pagar a Andina.</p>
        <p className="cc-small sim-result__note">Con este plan aún no conviene sacar plata para la casa.</p>
      </section>
    )

  if (estado === 'justo')
    return (
      <section className={cls}>
        <p className="sim-result__kicker">Justo</p>
        <p>Tu caja el {fecha} después de pagar:</p>
        <p className="sim-result__amount display num">{soles(saldo)}</p>
        <p className="sim-result__main">
          Te alcanza para pagar, pero quedas debajo de tu mínimo de {soles(MINIMO)}.
        </p>
        {mejora > 0 && (
          <p className="cc-small sim-result__note num">{soles(mejora, { sign: true })} mejor que no hacer nada.</p>
        )}
        <p className="cc-small sim-result__note">Todavía no conviene sacar plata para la casa.</p>
      </section>
    )

  return (
    <section className={cls}>
      <p className="sim-result__kicker">Te alcanza</p>
      <p>Después de pagar a Andina el {fecha}, te quedarían:</p>
      <p className="sim-result__amount display num">{soles(saldo)}</p>
      {mejora > 0 && (
        <p className="sim-result__main num">{soles(mejora, { sign: true })} mejor que no hacer nada.</p>
      )}
      <p className="cc-small sim-result__note">Pasas tu mínimo de {soles(MINIMO)} para el día a día.</p>
    </section>
  )
}

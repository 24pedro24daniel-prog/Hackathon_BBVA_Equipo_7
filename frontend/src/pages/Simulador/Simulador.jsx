import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../../api/index.js'
import { useApi } from '../../api/useApi.js'
import { ddmm, soles } from '../../lib/format.js'
import { ErrorState, LoadingBlock, MetaLine, PageHeader, Skeleton } from '../../components/ui/index.jsx'
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
      <PageHeader back sub="Antes del 30/11" title="¿Qué puedo hacer?" />
      <div className="sim-body">
        <div className="sim-options">
          <fieldset className="sim-group">
            <legend className="sim-legend">¿Cuánto le pides a Andina?</legend>
            <div className="sim-list">
              {OPCIONES.map((o) => (
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
                    <span className="sim-row__title num">{soles(o.monto)}</span>
                    <span className="sim-row__sub">{o.texto}</span>
                  </span>
                  <span className="sim-radio" aria-hidden="true" />
                </label>
              ))}
            </div>
          </fieldset>

          <fieldset className="sim-group">
            <legend className="sim-legend">También puedes</legend>
            <div className="sim-list">
              <label className="sim-row">
                <span className="sim-row__text">
                  <span className="sim-row__title">Pagar en 2 partes</span>
                  <span className="sim-row__sub">Mitad el 30/11 y mitad el 15/12 (pídelo a Andina)</span>
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

              {fiados.loading ? (
                <div className="sim-row" aria-hidden="true">
                  <Skeleton height={40} style={{ flex: 1 }} />
                </div>
              ) : fiados.error ? (
                <div className="sim-row">
                  <p className="cc-small cc-muted">
                    No pude traer tus fiados.{' '}
                    <button type="button" className="sim-link" onClick={fiados.reload}>
                      Intentar otra vez
                    </button>
                  </p>
                </div>
              ) : items.length ? (
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
              ) : null}
            </div>
          </fieldset>
        </div>

        <div className="sim-aside">
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
      <section className={cls} aria-labelledby="sim-result-title">
        <h2 id="sim-result-title" className="sim-result__title">
          No te alcanza.
        </h2>
        <p className="sim-result__label">Tu caja el {fecha} después de pagar</p>
        <p className="sim-result__amount display num">{soles(saldo)}</p>
        <p className="sim-result__main">Todavía te faltaría plata para pagar a Andina. Prueba combinar opciones.</p>
      </section>
    )

  if (estado === 'justo')
    return (
      <section className={cls} aria-labelledby="sim-result-title">
        <h2 id="sim-result-title" className="sim-result__title">
          Justo: te alcanza para pagar.
        </h2>
        <p className="sim-result__label">Tu caja el {fecha} después de pagar</p>
        <p className="sim-result__amount display num">{soles(saldo)}</p>
        <p className="sim-result__main">Pero quedas debajo de tu mínimo de {soles(MINIMO)}.</p>
        {mejora > 0 && (
          <p className="sim-result__note num">{soles(mejora, { sign: true })} mejor que no hacer nada.</p>
        )}
      </section>
    )

  return (
    <section className={cls} aria-labelledby="sim-result-title">
      <h2 id="sim-result-title" className="sim-result__title">
        Te alcanza.
      </h2>
      <p className="sim-result__label">Después de pagar a Andina el {fecha}, te quedarían</p>
      <p className="sim-result__amount display num">{soles(saldo)}</p>
      <p className="sim-result__main">Pasas tu mínimo de {soles(MINIMO)} para el día a día.</p>
      {mejora > 0 && <p className="sim-result__note num">{soles(mejora, { sign: true })} mejor que no hacer nada.</p>}
    </section>
  )
}

// Detalle de movimientos. Ruta oculta (/movimientos): no está en la navegación principal;
// se llega desde "Últimos movimientos → Ver detalle" en Inicio. ?id=MOV-… abre ese movimiento.
import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api } from '../../api/index.js'
import { useDemo } from '../../lib/useDemo.js'
import { hhmm, soles, weekdayDdmm } from '../../lib/format.js'
import { CANAL_LABEL, METODO_LABEL, TIPO_LABEL, esIngreso, tituloMovimiento } from '../../lib/movimientos.js'
import { Button, Card, ErrorState, Icon, LoadingBlock, Money, PageHeader, Status } from '../../components/ui/index.jsx'
import './Movimientos.css'

const PAGINA = 20
const CORTE = '2026-11-14' // fecha de la demo; con backend real se usaría la fecha de hoy

function etiquetaDia(fechaHora) {
  const dia = fechaHora.slice(0, 10)
  const ayer = new Date(`${CORTE}T12:00:00-05:00`)
  ayer.setDate(ayer.getDate() - 1)
  if (dia === CORTE) return 'Hoy'
  if (dia === ayer.toISOString().slice(0, 10)) return 'Ayer'
  return weekdayDdmm(fechaHora)
}

export default function Movimientos() {
  const [demo] = useDemo()
  const [params] = useSearchParams()
  const idInicial = params.get('id')
  const [items, setItems] = useState([])
  const [cursor, setCursor] = useState(null)
  const [estado, setEstado] = useState({ loading: true, error: null })
  const [abierto, setAbierto] = useState(idInicial)

  const cargar = (desde = null) => {
    setEstado({ loading: true, error: null })
    api.getMovimientos({ limit: PAGINA, cursor: desde }).then(
      (res) => {
        setItems((prev) => (desde ? [...prev, ...res.items] : res.items))
        setCursor(res.next_cursor)
        setEstado({ loading: false, error: null })
      },
      (error) => setEstado({ loading: false, error }),
    )
  }

  useEffect(() => cargar(null), [demo.escenario])

  // Al llegar con ?id, lleva la vista a ese movimiento
  useEffect(() => {
    if (!idInicial || !items.length) return
    document.getElementById(`mov-${idInicial}`)?.scrollIntoView({ block: 'center' })
  }, [idInicial, items.length])

  const grupos = useMemo(() => {
    const g = []
    for (const m of items) {
      const etiqueta = etiquetaDia(m.fecha_hora)
      const last = g[g.length - 1]
      if (last?.etiqueta === etiqueta) last.items.push(m)
      else g.push({ etiqueta, items: [m] })
    }
    return g
  }, [items])

  return (
    <div className="movs">
      <PageHeader back title="Tus movimientos" />
      <div className="movs__body">
        {estado.loading && !items.length ? (
          <LoadingBlock heights={[220, 220]} />
        ) : estado.error && !items.length ? (
          <ErrorState error={estado.error} onRetry={() => cargar(null)} />
        ) : !items.length ? (
          <Card>
            <p>Todavía no hay movimientos. Mándame tu primera venta por el chat.</p>
          </Card>
        ) : (
          <>
            {grupos.map((g) => (
              <section key={g.etiqueta} className="movs__grupo" aria-label={g.etiqueta}>
                <h2 className="movs__dia">{g.etiqueta}</h2>
                <Card flush>
                  <ul className="movs__lista">
                    {g.items.map((m) => (
                      <MovimientoItem
                        key={m.movimiento_id}
                        m={m}
                        abierto={abierto === m.movimiento_id}
                        onToggle={() => setAbierto((a) => (a === m.movimiento_id ? null : m.movimiento_id))}
                      />
                    ))}
                  </ul>
                </Card>
              </section>
            ))}
            {cursor && (
              <Button variant="secondary" block disabled={estado.loading} onClick={() => cargar(cursor)}>
                {estado.loading ? 'Cargando…' : 'Ver más'}
              </Button>
            )}
            {estado.error && items.length > 0 && <ErrorState error={estado.error} onRetry={() => cargar(cursor)} />}
          </>
        )}
      </div>
    </div>
  )
}

function MovimientoItem({ m, abierto, onToggle }) {
  const ingreso = esIngreso(m.tipo)
  const detalleId = `det-${m.movimiento_id}`
  return (
    <li id={`mov-${m.movimiento_id}`} className={abierto ? 'movs__item movs__item--open' : 'movs__item'}>
      <button type="button" className="movs__fila" aria-expanded={abierto} aria-controls={detalleId} onClick={onToggle}>
        <span className="movs__icono" aria-hidden="true">
          <Icon name={ingreso ? 'arrowDown' : 'arrowUp'} size={18} />
        </span>
        <span className="movs__main">
          <span className="movs__titulo">{tituloMovimiento(m)}</span>
          <span className="movs__sub">
            {hhmm(m.fecha_hora)} · {TIPO_LABEL[m.tipo] || 'Movimiento'}
          </span>
        </span>
        <span className="movs__monto">
          <Money value={ingreso ? m.monto : -m.monto} sign tone={ingreso ? 'pos' : 'neutral'} />
        </span>
        <Icon name="chevronDown" size={20} className="movs__chev" />
      </button>

      {abierto && (
        <dl className="movs__detalle" id={detalleId}>
          <Dato k="Qué fue" v={TIPO_LABEL[m.tipo] || m.tipo} />
          <Dato k="Cuándo" v={`${weekdayDdmm(m.fecha_hora)} a las ${hhmm(m.fecha_hora)}`} />
          <Dato k="Monto" v={soles(m.monto, { cents: true })} />
          <Dato k="Cómo se pagó" v={METODO_LABEL[m.metodo_pago] || m.metodo_pago} />
          {m.contraparte && <Dato k={ingreso ? 'De quién' : 'A quién'} v={m.contraparte} />}
          {m.items?.length > 0 && (
            <Dato
              k="Productos"
              v={
                <ul className="movs__productos">
                  {m.items.map((it, i) => (
                    <li key={it.producto_id || i}>
                      <span>
                        {it.cantidad} × {it.producto}
                      </span>
                      <span className="num">{soles(it.subtotal, { cents: true })}</span>
                    </li>
                  ))}
                </ul>
              }
            />
          )}
          <Dato k="Cómo lo anotaste" v={CANAL_LABEL[m.canal] || m.canal} />
          {m.afecta_caja === false ? (
            <Dato k="Tu caja" v={<Status tone="neutral">No mueve tu caja (es al crédito)</Status>} />
          ) : (
            m.saldo_post != null && <Dato k="Caja después" v={soles(m.saldo_post)} />
          )}
        </dl>
      )}
    </li>
  )
}

function Dato({ k, v }) {
  return (
    <div className="movs__dato">
      <dt>{k}</dt>
      <dd>{v}</dd>
    </div>
  )
}

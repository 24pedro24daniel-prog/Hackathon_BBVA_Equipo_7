// Detalle de movimientos. Ruta oculta (/movimientos): no está en la navegación principal;
// se llega desde "Últimos movimientos → Ver detalle" en Inicio. ?id=MOV-… abre ese movimiento;
// ?tipo=retiro_personal (u otro tipo del contrato) filtra la lista, p. ej. desde la alerta de retiros.
import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api } from '../../api/index.js'
import { useApi } from '../../api/useApi.js'
import { daysBetween, hhmm, soles, weekdayDdmm } from '../../lib/format.js'
import { CANAL_LABEL, METODO_LABEL, TIPO_LABEL, esIngreso, tituloMovimiento } from '../../lib/movimientos.js'
import { Button, Card, ErrorState, Icon, LoadingBlock, Money, PageHeader, Status } from '../../components/ui/index.jsx'
import './Movimientos.css'

const PAGINA = 20
/** "Hoy" / "Ayer" respecto a la fecha de corte del backend (resumen.corte); si no llegó, el día de la semana. */
function etiquetaDia(fechaHora, corte) {
  const dias = corte ? daysBetween(fechaHora.slice(0, 10), corte) : null
  if (dias === 0) return 'Hoy'
  if (dias === 1) return 'Ayer'
  return weekdayDdmm(fechaHora)
}

export default function Movimientos() {
  const corte = useApi(() => api.getResumen(), []).data?.corte
  const [params] = useSearchParams()
  const idInicial = params.get('id')
  const tipo = params.get('tipo') || undefined
  const [items, setItems] = useState([])
  const [cursor, setCursor] = useState(null)
  const [estado, setEstado] = useState({ loading: true, error: null })
  const [abierto, setAbierto] = useState(idInicial)

  const cargar = (desde = null) => {
    setEstado({ loading: true, error: null })
    api.getMovimientos({ limit: PAGINA, cursor: desde, tipo }).then(
      (res) => {
        setItems((prev) => (desde ? [...prev, ...res.items] : res.items))
        setCursor(res.next_cursor)
        setEstado({ loading: false, error: null })
      },
      (error) => setEstado({ loading: false, error }),
    )
  }

  useEffect(() => {
    setItems([])
    cargar(null)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tipo])

  // Al llegar con ?id, lleva la vista a ese movimiento
  useEffect(() => {
    if (!idInicial || !items.length) return
    document.getElementById(`mov-${idInicial}`)?.scrollIntoView({ block: 'center' })
  }, [idInicial, items.length])

  const grupos = useMemo(() => {
    const g = []
    for (const m of items) {
      const etiqueta = etiquetaDia(m.fecha_hora, corte)
      const last = g[g.length - 1]
      if (last?.etiqueta === etiqueta) last.items.push(m)
      else g.push({ etiqueta, items: [m] })
    }
    return g
  }, [items, corte])

  return (
    <div className="movs">
      <PageHeader back title="Tus movimientos" />
      <div className="movs__body">
        {tipo && (
          <p className="cc-muted cc-small movs__filtro">
            Solo: {TIPO_LABEL[tipo] || tipo.replace(/_/g, ' ')} ·{' '}
            <Link to="/app/movimientos" className="movs__filtro-link">
              Ver todos
            </Link>
          </p>
        )}
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
          <Money value={ingreso ? m.monto : -m.monto} tone={ingreso ? 'neutral' : 'neg'} />
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
                    <li key={i}>
                      <span>
                        {it.cantidad} × {it.producto || 'Producto'}
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

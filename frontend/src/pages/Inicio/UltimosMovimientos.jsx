import { useId, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../api/index.js'
import { useApi } from '../../api/useApi.js'
import { hhmm, weekdayDdmm } from '../../lib/format.js'
import { esIngreso, tituloMovimiento } from '../../lib/movimientos.js'
import { Card, Icon, List, ListRow, Money, Skeleton, ErrorState } from '../../components/ui/index.jsx'

const LIMITE = 5

/** Tarjeta desplegable con los últimos 5 movimientos y enlace a su detalle (/movimientos, ruta oculta). */
export default function UltimosMovimientos({ escenario }) {
  const [abierto, setAbierto] = useState(true)
  const id = useId()
  const movs = useApi(() => api.getMovimientos({ limit: LIMITE }), [escenario])
  const items = movs.data?.items ?? []

  return (
    <Card flush className="inicio__movs">
      <button
        type="button"
        className="inicio__movs-toggle"
        aria-expanded={abierto}
        aria-controls={id}
        onClick={() => setAbierto((a) => !a)}
      >
        <span className="inicio__movs-title">Últimos movimientos</span>
        <Icon name="chevronDown" size={20} className="inicio__movs-chev" />
      </button>

      {abierto && (
        <div id={id}>
          {movs.loading && !movs.data ? (
            <div className="inicio__movs-pad">
              <Skeleton height={160} />
            </div>
          ) : movs.error ? (
            <div className="inicio__movs-pad">
              <ErrorState error={movs.error} onRetry={movs.reload} />
            </div>
          ) : items.length === 0 ? (
            <p className="inicio__movs-pad cc-muted">Todavía no anotaste movimientos. Mándame tu primera venta por el chat.</p>
          ) : (
            <>
              <List>
                {items.map((m) => {
                  const ingreso = esIngreso(m.tipo)
                  return (
                    <ListRow
                      key={m.movimiento_id}
                      to={`/movimientos?id=${m.movimiento_id}`}
                      lead={<Icon name={ingreso ? 'arrowDown' : 'arrowUp'} size={18} />}
                      title={tituloMovimiento(m)}
                      sub={`${weekdayDdmm(m.fecha_hora)} · ${hhmm(m.fecha_hora)}${m.afecta_caja === false ? ' · no mueve tu caja' : ''}`}
                      amount={<Money value={ingreso ? m.monto : -m.monto} sign tone={ingreso ? 'pos' : 'neutral'} />}
                      chevron={false}
                    />
                  )
                })}
              </List>
              <Link to="/movimientos" className="inicio__movs-ver">
                Ver detalle <span aria-hidden="true">→</span>
              </Link>
            </>
          )}
        </div>
      )}
    </Card>
  )
}

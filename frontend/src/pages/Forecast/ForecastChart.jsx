import { useId, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { ddmm, soles, solesRange, weekdayDdmm } from '../../lib/format.js'

// Gráfico de 30 días dibujado a mano (SVG, sin librería), estilo Monzo "Balance" / SoFi "target line".
// El viewBox sigue el ancho real del contenedor (1 unidad = 1 px): el texto no crece y el alto se limita.
// A la derecha queda una columna para las etiquetas del eje y el valor final.
const PAD = { top: 12, right: 72, bottom: 28, left: 2 }
const MIN_W = 280
const MIN_H = 200
const MAX_H = 300

function useWidth(ref, fallback) {
  const [w, setW] = useState(fallback)
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    const measure = () => {
      const cw = Math.round(el.getBoundingClientRect().width)
      if (cw > 0) setW(cw)
    }
    measure()
    if (typeof ResizeObserver === 'undefined') return
    const ro = new ResizeObserver(measure)
    ro.observe(el)
    return () => ro.disconnect()
  }, [ref])
  return w
}

/** Hasta 3 marcas "redondas" dentro de [lo, hi] (incluye el 0 si cae en el rango). */
function niceTicks(lo, hi) {
  const span = hi - lo
  if (!(span > 0)) return [lo]
  const mag = 10 ** Math.floor(Math.log10(span / 2))
  for (const m of [1, 2, 2.5, 5, 10, 20, 25, 50]) {
    const step = m * mag
    const ticks = []
    for (let v = Math.ceil(lo / step) * step; v <= hi; v += step) ticks.push(Math.round(v))
    if (ticks.length <= 3) return ticks
  }
  return [lo, hi]
}

/**
 * points: [{ fecha, p10, p50, p90, hoy? }]
 * sel / onSel: día elegido (índice) — lo controla la página para mostrarlo en la cabecera de la tarjeta.
 */
export default function ForecastChart({ points, minimo, worstFecha, sel, onSel }) {
  const clipId = 'fc-clip-' + useId().replace(/[^a-zA-Z0-9_-]/g, '')
  const svgRef = useRef(null)
  const boxRef = useRef(null)
  const W = Math.max(MIN_W, useWidth(boxRef, 320))
  const H = Math.round(Math.min(MAX_H, Math.max(MIN_H, W * 0.5)))
  const PLOT_W = W - PAD.left - PAD.right
  const PLOT_H = H - PAD.top - PAD.bottom

  const geo = useMemo(() => {
    const n = points.length
    let lo = Math.min(0, minimo ?? 0, ...points.map((p) => p.p10))
    let hi = Math.max(minimo ?? 0, ...points.map((p) => p.p90))
    const pad = (hi - lo) * 0.06
    lo -= pad
    hi += pad
    const step = n > 1 ? PLOT_W / (n - 1) : PLOT_W
    const x = (i) => PAD.left + i * step
    const y = (v) => PAD.top + ((hi - v) / (hi - lo)) * PLOT_H
    const f = (v) => v.toFixed(1)
    const p50 = points.map((p, i) => `${i ? 'L' : 'M'}${f(x(i))},${f(y(p.p50))}`).join('')
    const band =
      points.map((p, i) => `${i ? 'L' : 'M'}${f(x(i))},${f(y(p.p90))}`).join('') +
      points
        .map((p, i) => [i, p])
        .reverse()
        .map(([i, p]) => `L${f(x(i))},${f(y(p.p10))}`)
        .join('') +
      'Z'
    let worst = points.findIndex((p) => p.fecha === worstFecha)
    if (worst < 0) worst = points.reduce((m, p, i) => (p.p50 < points[m].p50 ? i : m), 0)
    const risk = minimo == null ? [] : points.map((p, i) => (p.p50 < minimo ? i : -1)).filter((i) => i >= 0)
    const xTicks = n > 2 ? [0, Math.round((n - 1) / 2), n - 1] : points.map((_, i) => i)
    return { n, step, x, y, p50, band, worst, risk, xTicks, yTicks: niceTicks(lo, hi) }
  }, [points, minimo, worstFecha, PLOT_W, PLOT_H])

  const { n, step, x, y, worst, risk, xTicks, yTicks } = geo

  const pickFromPointer = (e) => {
    const r = svgRef.current?.getBoundingClientRect()
    if (!r || !r.width) return
    const vx = ((e.clientX - r.left) / r.width) * W
    const i = Math.round((vx - PAD.left) / step)
    onSel(Math.max(0, Math.min(n - 1, i)))
  }

  const onKey = (e) => {
    const cur = sel ?? 0
    if (e.key === 'ArrowRight') onSel(Math.min(n - 1, sel === null ? 0 : cur + 1))
    else if (e.key === 'ArrowLeft') onSel(Math.max(0, sel === null ? 0 : cur - 1))
    else if (e.key === 'Home') onSel(0)
    else if (e.key === 'End') onSel(n - 1)
    else if (e.key === 'Escape') onSel(null)
    else return
    e.preventDefault()
  }

  const firstRisk = risk[0]
  const lastRisk = risk[risk.length - 1]
  const summary =
    `Hoy tienes ${soles(points[0].p50)}. ` +
    `Lo esperado llega a su punto más bajo el ${ddmm(points[worst].fecha)}, con ${soles(points[worst].p50)}. ` +
    (minimo == null
      ? ''
      : risk.length
        ? `Estarías por debajo del mínimo de ${soles(minimo)} durante ${risk.length} días, del ${ddmm(points[firstRisk].fecha)} al ${ddmm(points[lastRisk].fecha)}.`
        : `No bajarías del mínimo de ${soles(minimo)}.`)

  const p = sel !== null && sel !== undefined ? points[sel] : null
  const xmin = PAD.left
  const xmax = PAD.left + PLOT_W
  const last = points[n - 1]
  const endY = y(last.p50)
  const endRisk = minimo != null && last.p50 < minimo
  // Valor final (2 líneas) en la columna derecha, sin salirse del gráfico.
  const endLabelY = Math.min(Math.max(endY + 4, PAD.top + 10), H - 20)
  // Etiquetas del eje y que no choquen con el valor final.
  const yLabels = yTicks.filter((v) => Math.abs(y(v) + 4 - (endLabelY + 7)) > 20)
  // Etiqueta del mínimo: arriba de la línea, salvo que no quepa.
  const minY = minimo != null ? y(minimo) : 0
  const minLabelY = minY - 6 < PAD.top + 10 ? minY + 14 : minY - 6

  return (
    <figure className="fc-chart">
      <figcaption className="sr-only">{summary} El detalle día por día está en la tabla siguiente.</figcaption>
      <div
        ref={boxRef}
        className="fc-chart__plot"
        tabIndex={0}
        role="group"
        aria-label="Gráfico de tu caja. Usa las flechas izquierda y derecha para recorrer los días."
        onKeyDown={onKey}
      >
        <svg
          ref={svgRef}
          viewBox={`0 0 ${W} ${H}`}
          width="100%"
          aria-hidden="true"
          focusable="false"
          onPointerDown={pickFromPointer}
          onPointerMove={pickFromPointer}
          onPointerLeave={(e) => e.pointerType === 'mouse' && onSel(null)}
        >
          {/* Rejilla tenue + etiquetas del eje y (máx. 3, a la derecha) */}
          {yTicks.map((v) => (
            <line key={`g${v}`} className="fc-grid" x1={xmin} x2={xmax} y1={y(v)} y2={y(v)} />
          ))}
          {yLabels.map((v) => (
            <text key={`t${v}`} className="fc-ylabel" x={W - 2} y={y(v) + 4} textAnchor="end">
              {soles(v)}
            </text>
          ))}

          {/* Rango posible (peor–mejor caso) */}
          <path className="fc-band" d={geo.band} />

          {/* Mínimo operativo: punteada con su etiqueta en línea, a la derecha */}
          {minimo != null && (
            <g>
              <line className="fc-min" x1={xmin} x2={xmax} y1={minY} y2={minY} />
              <text className="fc-min-label" x={xmax - 2} y={minLabelY} textAnchor="end">
                Mínimo {soles(minimo)}
              </text>
            </g>
          )}

          {/* Lo esperado */}
          <path className="fc-line" d={geo.p50} />
          {/* Tramo debajo del mínimo: la misma línea en rojo, recortada bajo el mínimo */}
          {minimo != null && risk.length > 0 && (
            <>
              <clipPath id={clipId}>
                <rect x={0} y={minY} width={W} height={Math.max(0, H - minY)} />
              </clipPath>
              <path className="fc-line fc-line--risk" d={geo.p50} clipPath={`url(#${clipId})`} />
            </>
          )}

          {/* Punto más bajo, solo si está debajo del mínimo */}
          {risk.includes(worst) && worst !== n - 1 && (
            <circle className="fc-dot fc-dot--worst" cx={x(worst)} cy={y(points[worst].p50)} r={4} />
          )}

          {/* Final: marcador hueco + valor aproximado en la columna derecha */}
          <circle className={`fc-end${endRisk ? ' fc-end--risk' : ''}`} cx={x(n - 1)} cy={endY} r={4.5} />
          <text className="fc-end-label" x={W - 2} y={endLabelY} textAnchor="end">
            {soles(last.p50)}
          </text>
          <text className="fc-end-sub" x={W - 2} y={endLabelY + 14} textAnchor="end">
            aprox.
          </text>

          {/* Día elegido */}
          {p && (
            <g>
              <line className="fc-cross" x1={x(sel)} x2={x(sel)} y1={PAD.top} y2={PAD.top + PLOT_H} />
              <circle className="fc-dot fc-dot--sel" cx={x(sel)} cy={y(p.p50)} r={5} />
            </g>
          )}

          {/* Eje x: primero, medio y último día */}
          {xTicks.map((i, k) => (
            <text
              key={i}
              className="fc-tick"
              x={x(i)}
              y={H - 8}
              textAnchor={k === 0 ? 'start' : k === xTicks.length - 1 ? 'end' : 'middle'}
            >
              {ddmm(points[i].fecha)}
            </text>
          ))}
        </svg>
      </div>

      <p className="sr-only" aria-live="polite">
        {p
          ? `${p.hoy ? 'Hoy' : weekdayDdmm(p.fecha)}: ${soles(p.p50)}` +
            (p.hoy ? '' : `, entre ${solesRange([p.p10, p.p90])}`)
          : ''}
      </p>

      <table className="sr-only">
        <caption>Tu caja día por día</caption>
        <thead>
          <tr>
            <th scope="col">Día</th>
            <th scope="col">Lo esperado</th>
            <th scope="col">Peor caso</th>
            <th scope="col">Mejor caso</th>
          </tr>
        </thead>
        <tbody>
          {points.map((d) => (
            <tr key={d.fecha}>
              <th scope="row">{weekdayDdmm(d.fecha)}</th>
              <td>{soles(d.p50)}</td>
              <td>{soles(d.p10)}</td>
              <td>{soles(d.p90)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </figure>
  )
}

import { useId, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { ddmm, soles, solesRange, weekdayDdmm } from '../../lib/format.js'

// Gráfico de 30 días dibujado a mano (SVG, sin librería). El viewBox sigue el ancho real del contenedor
// (1 unidad = 1 px), así el texto no crece y el alto se limita en pantallas anchas.
const PAD = { top: 10, right: 6, bottom: 26, left: 6 }
const MIN_W = 280
const MIN_H = 196
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

export default function ForecastChart({ points, minimo, worstFecha }) {
  const [sel, setSel] = useState(null)
  const clipId = 'fc-clip-' + useId().replace(/[^a-zA-Z0-9_-]/g, '')
  const svgRef = useRef(null)
  const boxRef = useRef(null)
  const W = Math.max(MIN_W, useWidth(boxRef, 320))
  const H = Math.round(Math.min(MAX_H, Math.max(MIN_H, W * 0.42)))
  const PLOT_W = W - PAD.left - PAD.right
  const PLOT_H = H - PAD.top - PAD.bottom

  const geo = useMemo(() => {
    const n = points.length
    const lows = points.map((p) => p.p10)
    const highs = points.map((p) => p.p90)
    let lo = Math.min(0, minimo ?? 0, ...lows)
    let hi = Math.max(minimo ?? 0, ...highs)
    const pad = (hi - lo) * 0.06
    lo -= pad
    hi += pad
    const step = n > 1 ? PLOT_W / (n - 1) : PLOT_W
    const x = (i) => PAD.left + i * step
    const y = (v) => PAD.top + ((hi - v) / (hi - lo)) * PLOT_H
    const line = (key) => points.map((p, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(p[key]).toFixed(1)}`).join('')
    const band =
      points.map((p, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(p.p90).toFixed(1)}`).join('') +
      points
        .map((p, i) => [i, p])
        .reverse()
        .map(([i, p]) => `L${x(i).toFixed(1)},${y(p.p10).toFixed(1)}`)
        .join('') +
      'Z'
    let worst = points.findIndex((p) => p.fecha === worstFecha)
    if (worst < 0) worst = points.reduce((m, p, i) => (p.p50 < points[m].p50 ? i : m), 0)
    const risk = minimo == null ? [] : points.map((p, i) => (p.p50 < minimo ? i : -1)).filter((i) => i >= 0)
    const ticks = points.map((_, i) => i).filter((i) => i % 7 === 0)
    return { n, step, x, y, p50: line('p50'), band, worst, risk, ticks }
  }, [points, minimo, worstFecha, PLOT_W, PLOT_H])

  const { n, step, x, y, worst, risk, ticks } = geo

  const pickFromPointer = (e) => {
    const r = svgRef.current?.getBoundingClientRect()
    if (!r || !r.width) return
    const vx = ((e.clientX - r.left) / r.width) * W
    const i = Math.round((vx - PAD.left) / step)
    setSel(Math.max(0, Math.min(n - 1, i)))
  }

  const onKey = (e) => {
    const cur = sel ?? 0
    if (e.key === 'ArrowRight') setSel(Math.min(n - 1, sel === null ? 0 : cur + 1))
    else if (e.key === 'ArrowLeft') setSel(Math.max(0, sel === null ? 0 : cur - 1))
    else if (e.key === 'Home') setSel(0)
    else if (e.key === 'End') setSel(n - 1)
    else if (e.key === 'Escape') setSel(null)
    else return
    e.preventDefault()
  }

  const firstRisk = risk[0]
  const lastRisk = risk[risk.length - 1]
  const summary =
    `Hoy tienes ${soles(points[0].p50)}. ` +
    `Lo esperado llega a su punto más bajo el ${ddmm(points[worst].fecha)}, con ${soles(points[worst].p50)}. ` +
    (risk.length
      ? `Estarías por debajo del mínimo de ${soles(minimo)} durante ${risk.length} días, del ${ddmm(points[firstRisk].fecha)} al ${ddmm(points[lastRisk].fecha)}.`
      : `No bajarías del mínimo de ${soles(minimo)}.`)

  const p = sel !== null ? points[sel] : null
  const xmin = PAD.left
  const xmax = W - PAD.right

  return (
    <figure className="fc-chart">
      <figcaption className="sr-only">
        {summary} El detalle día por día está en la tabla siguiente.
      </figcaption>
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
          onPointerLeave={(e) => e.pointerType === 'mouse' && setSel(null)}
        >
          {/* Rango mejor–peor (p10–p90) */}
          <path className="fc-band" d={geo.band} />
          {/* Cero */}
          <line className="fc-zero" x1={xmin} x2={xmax} y1={y(0)} y2={y(0)} />
          {/* Mínimo operativo: línea punteada sutil con su etiqueta */}
          {minimo != null && (
            <g>
              <line className="fc-min" x1={xmin} x2={xmax} y1={y(minimo)} y2={y(minimo)} />
              <text className="fc-min-label" x={xmax} y={y(minimo) - 6} textAnchor="end">
                Mínimo {soles(minimo)}
              </text>
            </g>
          )}
          {/* Lo esperado (p50) */}
          <path className="fc-line" d={geo.p50} />
          {/* Tramo bajo el mínimo: la misma línea en color de alerta, recortada debajo del mínimo */}
          {minimo != null && risk.length > 0 && (
            <>
              <clipPath id={clipId}>
                <rect x={0} y={y(minimo)} width={W} height={Math.max(0, H - y(minimo))} />
              </clipPath>
              <path className="fc-line fc-line--risk" d={geo.p50} clipPath={`url(#${clipId})`} />
            </>
          )}
          {/* Selección */}
          {p && (
            <g>
              <line className="fc-cross" x1={x(sel)} x2={x(sel)} y1={PAD.top} y2={PAD.top + PLOT_H} />
              <circle className="fc-dot fc-dot--sel" cx={x(sel)} cy={y(p.p50)} r={4} />
            </g>
          )}
          {/* Peor día: marcador de alerta solo si cae bajo el mínimo */}
          {risk.includes(worst) && (
            <circle className="fc-dot fc-dot--worst" cx={x(worst)} cy={y(points[worst].p50)} r={4.5} />
          )}
          {/* Eje x */}
          {ticks.map((i) => (
            <text
              key={i}
              className="fc-tick"
              x={x(i)}
              y={H - 8}
              textAnchor={i === 0 ? 'start' : i === n - 1 ? 'end' : 'middle'}
            >
              {ddmm(points[i].fecha)}
            </text>
          ))}
        </svg>
      </div>

      <p className="fc-readout" aria-live="polite">
        {p ? (
          <>
            <strong>{p.hoy ? 'Hoy' : weekdayDdmm(p.fecha)}</strong>
            {' · '}
            <span className="num">{soles(p.p50)}</span>
            {!p.hoy && (
              <span className="fc-readout__range num"> · entre {solesRange([p.p10, p.p90])}</span>
            )}
          </>
        ) : (
          <span className="cc-muted">Toca un día para ver su detalle.</span>
        )}
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

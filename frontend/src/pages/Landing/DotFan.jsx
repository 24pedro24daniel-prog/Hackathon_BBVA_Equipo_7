// Textura de la marca: el abanico de un pronóstico de caja dibujado con puntos.
// Cada línea es un camino posible del saldo en los próximos días; se abren hacia la derecha (más lejos, más incertidumbre)
// y bajan cerca del pago grande antes de subir. Puramente decorativa.

const W = 1200
const H = 720
const LINEAS = 15
const PASO = 20

function base(t) {
  // Sube suave, cae en el "pago del 30" (t ≈ 0.62) y se recupera.
  const caida = 120 * Math.exp(-((t - 0.62) ** 2) / 0.012)
  return 520 - 250 * t + 36 * Math.sin(t * Math.PI * 3.2) + caida
}

function camino(k) {
  const centro = (LINEAS - 1) / 2
  const pts = []
  for (let x = -20; x <= W + 20; x += PASO) {
    const t = Math.max(0, x / W)
    const abre = 30 + 150 * t ** 1.5 // ya separadas en el borde izquierdo: puntos, no rayas
    const y = base(t) + (k - centro) * (abre / centro) * 1.6
    pts.push(`${x.toFixed(0)} ${y.toFixed(1)}`)
  }
  return `M${pts.join('L')}`
}

const CAMINOS = Array.from({ length: LINEAS }, (_, k) => {
  const centro = (LINEAS - 1) / 2
  const lejania = Math.abs(k - centro) / centro // 0 en el centro (el valor esperado), 1 en los bordes
  return { d: camino(k), opacidad: (0.62 - 0.46 * lejania).toFixed(2), central: k === centro }
})

export default function DotFan({ className }) {
  return (
    <svg
      className={className}
      viewBox={`0 0 ${W} ${H}`}
      preserveAspectRatio="xMidYMid slice"
      aria-hidden="true"
      focusable="false"
    >
      <g fill="none" strokeLinecap="round">
        {CAMINOS.map((c, i) => (
          <path
            key={i}
            d={c.d}
            stroke="currentColor"
            strokeOpacity={c.opacidad}
            strokeWidth={c.central ? 3.6 : 2.8}
            strokeDasharray="0 11"
          />
        ))}
      </g>
    </svg>
  )
}

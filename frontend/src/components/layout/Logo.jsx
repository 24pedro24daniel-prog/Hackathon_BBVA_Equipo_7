/**
 * Marca de CajaClara: una caja abierta de la que sale la línea del pronóstico, subiendo.
 * El cuadrado toma `currentColor` (por defecto Electric vía CSS); el trazo de la caja es blanco
 * y la línea, light blue. Decorativa: el nombre lo da el texto vecino.
 */
export function LogoMark({ size = 32, className }) {
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 32 32"
      aria-hidden="true"
      focusable="false"
    >
      <rect width="32" height="32" rx="8" fill="currentColor" />
      <path
        d="M7.5 15v8a2 2 0 0 0 2 2h13a2 2 0 0 0 2-2v-8"
        fill="none"
        stroke="#ffffff"
        strokeWidth="2.75"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M11 19.5l4-4 3 2.5 5.5-7"
        fill="none"
        stroke="#85C8FF"
        strokeWidth="2.75"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="24" cy="10" r="2.25" fill="#85C8FF" />
    </svg>
  )
}

export default LogoMark

import { Navigate, useLocation } from 'react-router-dom'
import { useSesion } from '../../lib/useSesion.js'
import { ultimoMotivoSalida } from '../../lib/sesion.js'

/**
 * La app (/app/*) solo se ve con sesión. Sin sesión → /ingresar, recordando a dónde iba y por qué salió
 * (sesión vencida o cerrada) para explicarlo en el login.
 */
export default function RequireAuth({ children }) {
  const sesion = useSesion()
  const { pathname, search } = useLocation()
  if (!sesion) {
    return <Navigate to="/ingresar" replace state={{ desde: `${pathname}${search}`, motivo: ultimoMotivoSalida() }} />
  }
  return children
}

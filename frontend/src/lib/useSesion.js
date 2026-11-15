import { useEffect, useState } from 'react'
import { EVENTO_SESION, getSesion } from './sesion.js'

/** const sesion = useSesion(): la sesión actual (o null). Se actualiza al entrar, al salir y cuando el backend responde 401. */
export function useSesion() {
  const [sesion, set] = useState(getSesion)
  useEffect(() => {
    const on = () => set(getSesion())
    window.addEventListener(EVENTO_SESION, on)
    return () => window.removeEventListener(EVENTO_SESION, on)
  }, [])
  return sesion
}

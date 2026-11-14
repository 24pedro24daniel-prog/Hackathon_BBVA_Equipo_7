import { useEffect, useState } from 'react'
import { getDemoSettings, setDemoSettings } from './demo.js'

/** const [demo, setDemo] = useDemo(); demo.escenario ('pedro' | 'sano' | 'nuevo'), demo.fallback (bool) */
export function useDemo() {
  const [demo, set] = useState(getDemoSettings)
  useEffect(() => {
    const on = (e) => set(e.detail)
    window.addEventListener('cajaclara-demo', on)
    return () => window.removeEventListener('cajaclara-demo', on)
  }, [])
  return [demo, setDemoSettings]
}

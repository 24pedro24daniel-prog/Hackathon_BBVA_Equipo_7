import { useEffect, useState } from 'react'
import { getDemoSettings, setDemoSettings } from './demo.js'

/** const [demo, setDemo] = useDemo(); demo.tecnico (bool), demo.fallback (bool, solo mocks) */
export function useDemo() {
  const [demo, set] = useState(getDemoSettings)
  useEffect(() => {
    const on = (e) => set(e.detail)
    window.addEventListener('tucaserito-demo', on)
    return () => window.removeEventListener('tucaserito-demo', on)
  }, [])
  return [demo, setDemoSettings]
}

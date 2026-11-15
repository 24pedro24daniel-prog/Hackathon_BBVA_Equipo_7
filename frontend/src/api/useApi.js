import { useCallback, useEffect, useRef, useState } from 'react'

/**
 * const { data, error, loading, reload } = useApi(() => api.getResumen(), [])
 * Ignora respuestas de llamadas viejas si las deps cambian antes de que terminen.
 */
export function useApi(fn, deps = []) {
  const [state, setState] = useState({ data: null, error: null, loading: true })
  const callId = useRef(0)

  const run = useCallback(() => {
    const id = ++callId.current
    setState((s) => ({ ...s, loading: true, error: null }))
    Promise.resolve()
      .then(fn)
      .then(
        (data) => id === callId.current && setState({ data, error: null, loading: false }),
        (error) => id === callId.current && setState({ data: null, error, loading: false }),
      )
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)

  useEffect(() => {
    run()
  }, [run])

  return { ...state, reload: run }
}

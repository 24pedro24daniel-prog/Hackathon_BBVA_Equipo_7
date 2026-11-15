import { useEffect } from 'react'

/** Título de la pestaña por pantalla (la SPA tiene un solo index.html). */
export function useTitulo(titulo) {
  useEffect(() => {
    const anterior = document.title
    document.title = titulo
    return () => {
      document.title = anterior
    }
  }, [titulo])
}

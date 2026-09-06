import { useCallback, useEffect, useRef, useState } from 'react'

export default function useApiResource(key, loader) {
  const [state, setState] = useState({ data: null, error: null, status: 'loading' })
  const [revision, setRevision] = useState(0)
  const request = useRef(0)
  const reload = useCallback(() => setRevision((value) => value + 1), [])

  useEffect(() => {
    const controller = new AbortController()
    const id = ++request.current
    setState((current) => ({ ...current, error: null, status: current.data ? 'refreshing' : 'loading' }))
    loader(controller.signal)
      .then((data) => id === request.current && setState({ data, error: null, status: 'success' }))
      .catch((error) => {
        if (error.name !== 'AbortError' && id === request.current) {
          setState((current) => ({ ...current, error, status: 'error' }))
        }
      })
    return () => controller.abort()
  }, [key, revision])
  return { ...state, reload }
}

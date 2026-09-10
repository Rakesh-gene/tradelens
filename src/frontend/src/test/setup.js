import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

if (typeof window.localStorage?.getItem !== 'function') {
  const values = new Map()
  Object.defineProperty(window, 'localStorage', {
    configurable: true,
    value: {
      clear: () => values.clear(),
      getItem: (key) => values.has(String(key)) ? values.get(String(key)) : null,
      removeItem: (key) => values.delete(String(key)),
      setItem: (key, value) => values.set(String(key), String(value)),
    },
  })
}

afterEach(() => cleanup())

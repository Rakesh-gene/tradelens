export function recordApiRequest({ method, path, status, durationMs, outcome }) {
  if (typeof window === 'undefined' || typeof window.dispatchEvent !== 'function' || typeof CustomEvent === 'undefined') return
  const route = path
    .replace(/[0-9a-f]{8}-[0-9a-f-]{27,}/gi, ':id')
    .replace(/INE[A-Z0-9]{9}/g, ':isin')
  window.dispatchEvent(new CustomEvent('tradelens:api-request', { detail: { method, path: route, status, durationMs: Math.round(durationMs), outcome } }))
}

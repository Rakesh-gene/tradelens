import { authenticatedRequest } from './authenticatedApi.js'

export function searchSecurities(query, options = {}) {
  return authenticatedRequest('/api/securities/search', { ...options, query })
}

export async function resolveSecuritySymbol(symbol, options = {}) {
  const normalized = String(symbol || '').trim().toUpperCase()
  const payload = await searchSecurities({ q: normalized, limit: 20 }, options)
  const security = (payload.items || []).find((item) => String(item.symbol || '').toUpperCase() === normalized)
  if (!security) {
    const error = new Error(`No security was found for symbol ${normalized}.`)
    error.status = 404
    throw error
  }
  return security
}

export function resolveIndexSecurity(code, options = {}) {
  return authenticatedRequest(`/api/indices/${encodeURIComponent(code)}/security`, options)
}

export function getSecurityFingerprint(isin, options = {}) {
  return authenticatedRequest(`/api/securities/${encodeURIComponent(isin)}/fingerprint`, options)
}

export function getSecurityChart(isin, query, options = {}) {
  return authenticatedRequest(`/api/securities/${encodeURIComponent(isin)}/chart`, { ...options, query })
}

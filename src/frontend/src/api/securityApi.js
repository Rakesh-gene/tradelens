import { authenticatedRequest } from './authenticatedApi.js'

export function searchSecurities(query, options = {}) {
  return authenticatedRequest('/api/securities/search', { ...options, query })
}

export function getSecurityFingerprint(isin, options = {}) {
  return authenticatedRequest(`/api/securities/${encodeURIComponent(isin)}/fingerprint`, options)
}

export function getSecurityChart(isin, query, options = {}) {
  return authenticatedRequest(`/api/securities/${encodeURIComponent(isin)}/chart`, { ...options, query })
}

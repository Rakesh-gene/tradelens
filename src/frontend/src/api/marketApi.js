import { authenticatedRequest } from './authenticatedApi.js'

export function getSectorRotation(query, options = {}) {
  return authenticatedRequest('/api/sectors/rotation', { ...options, query })
}

export function getSectorStocks(query, options = {}) {
  return authenticatedRequest('/api/sectors/stocks', { ...options, query })
}

export function getOverview(query, options = {}) {
  return authenticatedRequest('/api/overview', { ...options, query })
}

export function getSetups(query, options = {}) {
  return authenticatedRequest('/api/setups', { ...options, query })
}

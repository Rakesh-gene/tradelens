import { authenticatedRequest } from './authenticatedApi.js'

export function getOverview(query, options = {}) {
  return authenticatedRequest('/api/overview', { ...options, query })
}

export function getSetups(query, options = {}) {
  return authenticatedRequest('/api/setups', { ...options, query })
}

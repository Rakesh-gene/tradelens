import { authenticatedRequest } from './authenticatedApi.js'

export function getIndices(options = {}) {
  return authenticatedRequest('/api/indices', options)
}

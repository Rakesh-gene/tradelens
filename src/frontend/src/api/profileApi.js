import { authenticatedRequest } from './authenticatedApi.js'

export function updateProfile(preferences, options = {}) {
  return authenticatedRequest('/api/profile', { ...options, method: 'PATCH', body: preferences })
}

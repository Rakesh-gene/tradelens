import { authenticatedRequest } from './authenticatedApi.js'

export function getWatchlist(options = {}) {
  return authenticatedRequest('/api/watchlist', options)
}

export function addToWatchlist(isin, options = {}) {
  return authenticatedRequest('/api/watchlist', { ...options, method: 'POST', body: { isin } })
}

export function removeFromWatchlist(isin, options = {}) {
  return authenticatedRequest(`/api/watchlist/${encodeURIComponent(isin)}`, { ...options, method: 'DELETE' })
}

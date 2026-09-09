import { authenticatedRequest } from './authenticatedApi.js'

export function getPattern(patternId, options = {}) {
  return authenticatedRequest(`/api/patterns/${encodeURIComponent(patternId)}`, options)
}

export function getPatternEvents(patternId, query, options = {}) {
  return authenticatedRequest(`/api/patterns/${encodeURIComponent(patternId)}/events`, { ...options, query })
}

export function getPatternChart(patternId, query, options = {}) {
  return authenticatedRequest(`/api/patterns/${encodeURIComponent(patternId)}/chart`, { ...options, query })
}

import { authenticatedRequest } from './authenticatedApi.js'

export function getAdminEquities(query, options = {}) {
  return authenticatedRequest('/api/admin/equities', { ...options, query })
}

export function getPipelineRuns(query, options = {}) {
  return authenticatedRequest('/api/admin/pipeline/runs', { ...options, query })
}

export function getPipelineRun(runId, query, options = {}) {
  return authenticatedRequest(`/api/admin/pipeline/runs/${encodeURIComponent(runId)}`, { ...options, query })
}

export function createPipelineRun(body, options = {}) {
  return authenticatedRequest('/api/admin/pipeline/runs', { ...options, method: 'POST', body })
}

export function createPatternScan(body, options = {}) {
  return authenticatedRequest('/api/admin/pattern-scans', { ...options, method: 'POST', body })
}

export function controlPipelineRun(runId, action, options = {}) {
  return authenticatedRequest(`/api/admin/pipeline/runs/${encodeURIComponent(runId)}/${encodeURIComponent(action)}`, {
    ...options,
    method: 'POST',
    body: {},
  })
}

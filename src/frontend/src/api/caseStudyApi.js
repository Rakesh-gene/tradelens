import { authenticatedRequest } from './authenticatedApi.js'

export function getCaseStudies(query, options = {}) { return authenticatedRequest('/api/case-studies', { ...options, query }) }
export function getCaseStudy(caseStudyId, options = {}) { return authenticatedRequest(`/api/case-studies/${encodeURIComponent(caseStudyId)}`, options) }
export function getCaseStudyChart(caseStudyId, options = {}) { return authenticatedRequest(`/api/case-studies/${encodeURIComponent(caseStudyId)}/chart`, options) }
export function getCaseStudyFacets(options = {}) { return authenticatedRequest('/api/case-studies/facets', options) }

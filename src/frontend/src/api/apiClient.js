import { buildQuery } from '../utils/queryString.js'
import { recordApiRequest } from '../utils/observability.js'

export class ApiError extends Error {
  constructor(message, { status = 0, code = 'REQUEST_FAILED', details = null, requestId = null } = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.details = details
    this.requestId = requestId
  }
}

function requestPath(path, query) {
  if (typeof path !== 'string' || !path.startsWith('/api/')) {
    throw new TypeError('API paths must be relative and begin with /api/.')
  }
  const encoded = buildQuery(query)
  return encoded ? `${path}${path.includes('?') ? '&' : '?'}${encoded}` : path
}

async function responsePayload(response) {
  const contentType = response.headers.get('content-type') || ''
  if (!contentType.toLowerCase().includes('application/json')) {
    if (response.status === 204) return null
    throw new ApiError('The server returned an invalid response.', {
      status: response.status,
      code: 'INVALID_RESPONSE',
    })
  }
  try {
    return await response.json()
  } catch {
    throw new ApiError('The server returned invalid JSON.', {
      status: response.status,
      code: 'INVALID_RESPONSE',
    })
  }
}

function errorFrom(response, payload) {
  const envelope = payload?.error
  if (envelope && typeof envelope === 'object') {
    return new ApiError(envelope.message || 'TradeLens could not complete this request.', {
      status: response.status,
      code: envelope.code,
      details: envelope.details,
      requestId: envelope.requestId,
    })
  }
  return new ApiError(
    typeof envelope === 'string' ? envelope : 'TradeLens could not complete this request.',
    { status: response.status, code: response.status === 401 ? 'UNAUTHORIZED' : 'REQUEST_FAILED' },
  )
}

export async function apiRequest(path, { method = 'GET', body, token, signal, query } = {}) {
  const startedAt = performance.now()
  const url = requestPath(path, query)
  const headers = { Accept: 'application/json' }
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  if (token) headers.Authorization = `Bearer ${token}`

  let response
  try {
    response = await fetch(url, {
      method,
      signal,
      headers,
      ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
    })
  } catch (error) {
    if (error?.name === 'AbortError') throw error
    recordApiRequest({ method, path, status: 0, durationMs: performance.now() - startedAt, outcome: 'network-error' })
    throw new ApiError('TradeLens could not reach the server.', { code: 'NETWORK_ERROR' })
  }

  let payload
  try {
    payload = await responsePayload(response)
  } catch (error) {
    recordApiRequest({ method, path, status: response.status, durationMs: performance.now() - startedAt, outcome: 'invalid-response' })
    throw error
  }
  recordApiRequest({ method, path, status: response.status, durationMs: performance.now() - startedAt, outcome: response.ok ? 'success' : 'api-error' })
  if (!response.ok) throw errorFrom(response, payload)
  return payload
}

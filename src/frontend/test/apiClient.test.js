import test from 'node:test'
import assert from 'node:assert/strict'
import { ApiError, apiRequest } from '../src/api/apiClient.js'

test('encodes query values and sends JSON headers only when needed', async (context) => {
  const originalFetch = globalThis.fetch
  context.after(() => { globalThis.fetch = originalFetch })
  let request
  globalThis.fetch = async (path, options) => {
    request = { path, options }
    return new Response(JSON.stringify({ ok: true }), { headers: { 'Content-Type': 'application/json' } })
  }
  await apiRequest('/api/setups', { query: { state: ['READY', 'TRIGGERED'], blank: '', missing: null } })
  assert.equal(request.path, '/api/setups?state=READY&state=TRIGGERED')
  assert.equal(request.options.headers.Accept, 'application/json')
  assert.equal(request.options.headers['Content-Type'], undefined)
})

test('normalizes structured and transitional API errors', async (context) => {
  const originalFetch = globalThis.fetch
  context.after(() => { globalThis.fetch = originalFetch })
  globalThis.fetch = async () => new Response(JSON.stringify({ error: { code: 'INVALID_FILTER', message: 'Bad state', details: { field: 'state' }, requestId: 'req_1' } }), {
    status: 400,
    headers: { 'Content-Type': 'application/json' },
  })
  await assert.rejects(apiRequest('/api/setups'), (error) => {
    assert.ok(error instanceof ApiError)
    assert.equal(error.status, 400)
    assert.equal(error.code, 'INVALID_FILTER')
    assert.equal(error.requestId, 'req_1')
    return true
  })
})

test('rejects non-JSON and non-API responses predictably', async (context) => {
  const originalFetch = globalThis.fetch
  context.after(() => { globalThis.fetch = originalFetch })
  globalThis.fetch = async () => new Response('<html>proxy error</html>', { status: 502, headers: { 'Content-Type': 'text/html' } })
  await assert.rejects(apiRequest('/api/overview'), (error) => error.code === 'INVALID_RESPONSE' && error.status === 502)
  await assert.rejects(apiRequest('https://example.com/api/data'), TypeError)
})

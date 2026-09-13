import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { buildQuery } from '../src/utils/queryString.js'
import { clearAccessToken, readAccessToken, writeAccessToken } from '../src/auth/authSession.js'
import { formatCompactNumber, formatPercent, formatPrice, formatScore } from '../src/utils/formatters.js'
import { parseSetupFilters, setupQuery } from '../src/utils/setupFilters.js'
import { lifecycleTone } from '../src/utils/presentation.js'

test('query helper repeats arrays and omits empty values', () => {
  assert.equal(buildQuery({ state: ['READY', 'TRIGGERED'], pageSize: 25, empty: '', nil: null }), 'state=READY&state=TRIGGERED&pageSize=25')
})

test('session helper owns access-token storage', () => {
  const values = new Map()
  globalThis.window = { sessionStorage: { getItem: (key) => values.get(key) || null, setItem: (key, value) => values.set(key, value), removeItem: (key) => values.delete(key) } }
  writeAccessToken('token')
  assert.equal(readAccessToken(), 'token')
  clearAccessToken()
  assert.equal(readAccessToken(), null)
  delete globalThis.window
})

test('contract fixture freezes every Phase 0 response family', async () => {
  const fixture = JSON.parse(await readFile(new URL('./fixtures/pattern-engine-contracts.json', import.meta.url), 'utf8'))
  assert.deepEqual(Object.keys(fixture), ['error', 'freshness', 'setupSummary', 'patternDetail', 'event', 'fingerprint', 'chart'])
  assert.equal(fixture.setupSummary.security.isin, fixture.fingerprint.security.isin)
  assert.equal(fixture.chart.adjusted, true)
})

test('setup filters validate visible fields and omit removed advanced filters', () => {
  const parsed = parseSetupFilters('?state=READY&sort=qualityScore&direction=asc&variant=VCP-3C&minRs6m=91&minSetupScore=bad')
  assert.equal(parsed.filters.state, 'READY')
  assert.equal(parsed.filters.sort, 'qualityScore')
  assert.deepEqual(parsed.corrected, ['minSetupScore'])
  assert.equal(setupQuery(parsed.filters).minRs6m, undefined)
  assert.equal(setupQuery(parsed.filters).variant, undefined)
})

test('domain formatters preserve percentages and nulls', () => {
  assert.match(formatPrice(1234.5), /1,234\.50/)
  assert.equal(formatPercent(1.7), '1.7%')
  assert.equal(formatPercent(1.23456), '1.235%')
  assert.equal(formatPercent(1.7, { signed: true }), '+1.7%')
  assert.equal(formatScore(null), 'Not available')
  assert.match(formatCompactNumber(125000), /1\.25L|125K/)
})

test('lifecycle tone remains readable for known and future states', () => {
  assert.equal(lifecycleTone('READY'), 'actionable')
  assert.equal(lifecycleTone('CONFIRMED'), 'active')
  assert.equal(lifecycleTone('INVALIDATED'), 'terminal')
  assert.equal(lifecycleTone('FUTURE_STATE'), 'developing')
})

import test from 'node:test'
import assert from 'node:assert/strict'
import { buildIndexPath, buildPatternPath, buildSecurityPath, matchRoute } from '../src/routing/routes.js'

test('matches static and valid dynamic routes', () => {
  assert.equal(matchRoute('/overview/').name, 'overview')
  assert.equal(matchRoute('/sector-rotation/').name, 'sector-rotation')
  assert.equal(matchRoute('/profile').name, 'profile')
  assert.equal(matchRoute('/guide').name, 'guide')
  assert.equal(matchRoute('/watchlist').name, 'watchlist')
  assert.equal(matchRoute('/indices').name, 'indices')
  assert.equal(matchRoute('/indices').entitlement, 'indices')
  assert.deepEqual(matchRoute('/indices/nifty%20it').params, { code: 'NIFTY IT' })
  assert.equal(matchRoute('/case-studies').name, 'case-studies')
  assert.equal(matchRoute('/admin/case-studies').name, 'admin-case-studies')
  assert.deepEqual(matchRoute('/case-studies/2a9ca55f-3d2d-4b25-b683-36979029fb97').params, {
    caseStudyId: '2a9ca55f-3d2d-4b25-b683-36979029fb97',
  })
  assert.deepEqual(matchRoute('/patterns/2a9ca55f-3d2d-4b25-b683-36979029fb97').params, {
    patternId: '2a9ca55f-3d2d-4b25-b683-36979029fb97',
  })
  assert.deepEqual(matchRoute('/securities/reliance').params, { symbol: 'RELIANCE' })
})

test('rejects malformed identifiers locally', () => {
  assert.equal(matchRoute('/patterns/not-a-uuid').name, 'not-found')
  assert.equal(matchRoute('/securities/INE002A01018').name, 'not-found')
  assert.equal(matchRoute('/securities/INIDX0000200').name, 'not-found')
  assert.equal(matchRoute('/securities/RELIANCE').name, 'security')
  assert.equal(matchRoute('/missing').name, 'not-found')
  assert.equal(matchRoute('/research').name, 'not-found')
  assert.equal(matchRoute('/research/2a9ca55f-3d2d-4b25-b683-36979029fb97').name, 'not-found')
  assert.equal(matchRoute('/case-studies/not-a-uuid').name, 'not-found')
})

test('builds encoded, validated dynamic paths', () => {
  assert.equal(buildPatternPath('2a9ca55f-3d2d-4b25-b683-36979029fb97'), '/patterns/2a9ca55f-3d2d-4b25-b683-36979029fb97')
  assert.equal(buildSecurityPath('reliance'), '/securities/RELIANCE')
  assert.equal(buildIndexPath('nifty it'), '/indices/NIFTY%20IT')
  assert.throws(() => buildSecurityPath('INE002A01018'))
  assert.throws(() => buildIndexPath('INIDX0000200'))
  assert.throws(() => buildPatternPath('bad'))
})

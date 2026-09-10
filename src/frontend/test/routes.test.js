import test from 'node:test'
import assert from 'node:assert/strict'
import { buildPatternPath, buildSecurityPath, matchRoute } from '../src/routing/routes.js'

test('matches static and valid dynamic routes', () => {
  assert.equal(matchRoute('/overview/').name, 'overview')
  assert.equal(matchRoute('/profile').name, 'profile')
  assert.deepEqual(matchRoute('/patterns/2a9ca55f-3d2d-4b25-b683-36979029fb97').params, {
    patternId: '2a9ca55f-3d2d-4b25-b683-36979029fb97',
  })
  assert.deepEqual(matchRoute('/securities/ine002a01018').params, { isin: 'INE002A01018' })
})

test('rejects malformed identifiers locally', () => {
  assert.equal(matchRoute('/patterns/not-a-uuid').name, 'not-found')
  assert.equal(matchRoute('/securities/RELIANCE').name, 'not-found')
  assert.equal(matchRoute('/missing').name, 'not-found')
  assert.equal(matchRoute('/research').name, 'not-found')
  assert.equal(matchRoute('/research/2a9ca55f-3d2d-4b25-b683-36979029fb97').name, 'not-found')
})

test('builds encoded, validated dynamic paths', () => {
  assert.equal(buildPatternPath('2a9ca55f-3d2d-4b25-b683-36979029fb97'), '/patterns/2a9ca55f-3d2d-4b25-b683-36979029fb97')
  assert.equal(buildSecurityPath('ine002a01018'), '/securities/INE002A01018')
  assert.throws(() => buildPatternPath('bad'))
})

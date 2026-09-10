import { isIsin, isUuid, safeDecodeSegment } from '../utils/guards.js'

const STATIC_ROUTES = new Map([
  ['/', { name: 'login', protected: false }],
  ['/signup', { name: 'signup', protected: false }],
  ['/overview', { name: 'overview', protected: true }],
  ['/setups', { name: 'setups', protected: true }],
  ['/profile', { name: 'profile', protected: true }],
  ['/admin/pipeline', { name: 'admin-pipeline', protected: true, admin: true }],
])

export function normalizePathname(pathname) {
  const value = typeof pathname === 'string' ? pathname : '/'
  return value.replace(/\/+$/, '') || '/'
}

export function matchRoute(pathname) {
  const path = normalizePathname(pathname)
  const staticRoute = STATIC_ROUTES.get(path)
  if (staticRoute) return { ...staticRoute, params: {} }

  const patternMatch = path.match(/^\/patterns\/([^/]+)$/)
  if (patternMatch) {
    const patternId = safeDecodeSegment(patternMatch[1])
    return patternId && isUuid(patternId)
      ? { name: 'pattern-detail', protected: true, params: { patternId } }
      : { name: 'not-found', protected: true, params: {} }
  }

  const securityMatch = path.match(/^\/securities\/([^/]+)$/)
  if (securityMatch) {
    const isin = safeDecodeSegment(securityMatch[1])?.toUpperCase()
    return isin && isIsin(isin)
      ? { name: 'security', protected: true, params: { isin } }
      : { name: 'not-found', protected: true, params: {} }
  }

  return { name: 'not-found', protected: false, params: {} }
}

export function buildPatternPath(patternId) {
  if (!isUuid(patternId)) throw new TypeError('A valid pattern UUID is required.')
  return `/patterns/${encodeURIComponent(patternId)}`
}

export function buildSecurityPath(isin) {
  const normalized = String(isin || '').toUpperCase()
  if (!isIsin(normalized)) throw new TypeError('A valid ISIN is required.')
  return `/securities/${encodeURIComponent(normalized)}`
}

export function isProtectedRoute(route) {
  return Boolean(route?.protected)
}

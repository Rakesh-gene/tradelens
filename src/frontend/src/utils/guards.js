const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i
const ISIN_PATTERN = /^[A-Z]{2}[A-Z0-9]{9}[0-9]$/

export function isUuid(value) {
  return typeof value === 'string' && UUID_PATTERN.test(value)
}

export function isIsin(value) {
  return typeof value === 'string' && ISIN_PATTERN.test(value.toUpperCase())
}

export function isSecuritySlug(value) {
  if (typeof value !== 'string') return false
  const normalized = value.trim().toUpperCase()
  return !isIsin(normalized) && /^[A-Z0-9][A-Z0-9._&-]{0,30}$/.test(normalized)
}

export function isIndexCode(value) {
  if (typeof value !== 'string') return false
  const normalized = value.trim().toUpperCase()
  return !isIsin(normalized) && /^[A-Z0-9][A-Z0-9 .&-]{0,80}$/.test(normalized)
}

export function safeDecodeSegment(value) {
  try {
    return decodeURIComponent(value)
  } catch {
    return null
  }
}

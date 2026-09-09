const SETUPS_LOCATION_KEY = 'tradelensSetupsLocation'

function normalizeSetupsLocation(value) {
  if (!value) return null
  try {
    const location = new URL(value, window.location.origin)
    const pathname = location.pathname.replace(/\/+$/, '') || '/'
    if (location.origin !== window.location.origin || pathname !== '/setups') return null
    return `${pathname}${location.search}`
  } catch {
    return null
  }
}

export function rememberSetupsLocation(value = `${window.location.pathname}${window.location.search}`) {
  const normalized = normalizeSetupsLocation(value)
  if (!normalized) return
  window.sessionStorage.setItem(SETUPS_LOCATION_KEY, normalized)
}

export function rememberCurrentSetupsLocation() {
  if ((window.location.pathname.replace(/\/+$/, '') || '/') === '/setups') {
    rememberSetupsLocation()
  }
}

export function rememberedSetupsLocation() {
  return normalizeSetupsLocation(window.sessionStorage.getItem(SETUPS_LOCATION_KEY)) || '/setups'
}

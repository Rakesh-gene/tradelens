export const DEFAULT_WATCHLIST_VIEW = 'cards'
export const WATCHLIST_VIEW_STORAGE_KEY = 'tradelensWatchlistView'

const WATCHLIST_VIEWS = new Set(['cards', 'list', 'quadrant'])

export function normalizeWatchlistView(view) {
  return WATCHLIST_VIEWS.has(view) ? view : DEFAULT_WATCHLIST_VIEW
}

export function readWatchlistView() {
  try {
    return normalizeWatchlistView(window.localStorage.getItem(WATCHLIST_VIEW_STORAGE_KEY))
  } catch {
    return DEFAULT_WATCHLIST_VIEW
  }
}

export function saveWatchlistView(view) {
  const normalized = normalizeWatchlistView(view)
  try { window.localStorage.setItem(WATCHLIST_VIEW_STORAGE_KEY, normalized) } catch { /* storage may be unavailable */ }
  return normalized
}

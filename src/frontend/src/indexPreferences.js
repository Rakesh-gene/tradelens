export const INDEX_VIEW_STORAGE_KEY = 'tradelensIndexView'
const VIEWS = new Set(['cards', 'list', 'quadrant'])

export function normalizeIndexView(value) { return VIEWS.has(value) ? value : 'cards' }
export function readIndexView() {
  try { return normalizeIndexView(window.localStorage.getItem(INDEX_VIEW_STORAGE_KEY)) }
  catch { return 'cards' }
}
export function saveIndexView(value) {
  const normalized = normalizeIndexView(value)
  try { window.localStorage.setItem(INDEX_VIEW_STORAGE_KEY, normalized) } catch { /* unavailable */ }
  return normalized
}

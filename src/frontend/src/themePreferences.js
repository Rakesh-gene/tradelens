export const DEFAULT_THEME = 'ember'
export const THEME_STORAGE_KEY = 'tradelensTheme'

export const THEMES = [
  { id: 'light', name: 'White', description: 'Soft paper white with warm amber emphasis.' },
  { id: 'ember', name: 'Ember', description: 'Warm amber with grounded cocoa tones.' },
  { id: 'forest', name: 'Forest', description: 'Moss green with soft sage highlights.' },
  { id: 'ocean', name: 'Ocean', description: 'Deep teal with clear aqua accents.' },
  { id: 'plum', name: 'Plum', description: 'Aubergine with muted rose highlights.' },
  { id: 'slate', name: 'Slate', description: 'Blue slate with restrained copper accents.' },
]

const THEME_IDS = new Set(THEMES.map(({ id }) => id))

export function normalizeTheme(theme) {
  return THEME_IDS.has(theme) ? theme : DEFAULT_THEME
}

export function readTheme() {
  try {
    return normalizeTheme(window.localStorage.getItem(THEME_STORAGE_KEY))
  } catch {
    return DEFAULT_THEME
  }
}

export function applyTheme(theme, { persist = true } = {}) {
  const normalized = normalizeTheme(theme)
  if (typeof document !== 'undefined') document.documentElement.dataset.theme = normalized
  if (persist) {
    try { window.localStorage.setItem(THEME_STORAGE_KEY, normalized) } catch { /* storage may be unavailable */ }
  }
  return normalized
}

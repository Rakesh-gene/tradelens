import { beforeEach, describe, expect, it } from 'vitest'
import { applyTheme, DEFAULT_THEME, normalizeTheme, readTheme, THEME_STORAGE_KEY } from './themePreferences.js'

describe('theme preferences', () => {
  beforeEach(() => {
    localStorage.clear()
    delete document.documentElement.dataset.theme
  })

  it('rejects unsupported themes and defaults to ember', () => {
    expect(normalizeTheme('black')).toBe(DEFAULT_THEME)
    expect(readTheme()).toBe(DEFAULT_THEME)
  })

  it('applies and persists a supported theme', () => {
    expect(applyTheme('plum')).toBe('plum')
    expect(document.documentElement.dataset.theme).toBe('plum')
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('plum')
  })
})

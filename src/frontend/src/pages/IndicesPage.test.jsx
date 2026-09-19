import React from 'react'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import IndicesPage from './IndicesPage.jsx'
import { getIndices } from '../api/indicesApi.js'
import { INDEX_VIEW_STORAGE_KEY } from '../indexPreferences.js'

vi.mock('../api/indicesApi.js', () => ({ getIndices: vi.fn() }))

const item = {
  code: 'NIFTY IT', name: 'NIFTY IT', category: 'SECTORAL',
  dataAsOf: '2026-09-11', lastClose: 40000, dailyChangePct: 1.2,
  distanceTo52WeekHighPct: -3, relativeStrength1m: 6, relativeStrength3m: 9,
  relativeStrength6m: 12, relativeStrength12m: 18,
  trend: { aboveEma20: true, aboveSma50: true, aboveSma200: false },
  rotation: { strength: 9, momentum: 3, zone: 'LEADING', trail: [
    { date: '2026-09-05', strength: 5, momentum: 1 }, { date: '2026-09-08', strength: 6, momentum: 2 },
    { date: '2026-09-09', strength: 7, momentum: 2.5 }, { date: '2026-09-10', strength: 8, momentum: 2.7 },
    { date: '2026-09-11', strength: 9, momentum: 3 },
  ] },
  primarySetup: { patternInstanceId: '00000000-0000-4000-8000-000000000001', patternType: 'BASE-VCP', variant: 'VCP-3C', state: 'READY', setupScore: 84, pivotPrice: 40500, distanceToPivotPct: -1.23 },
}

beforeEach(() => {
  localStorage.clear(); window.history.replaceState({}, '', '/indices')
  getIndices.mockReset(); getIndices.mockResolvedValue({
    dataAsOf: '2026-09-11', count: 1, isStale: false, items: [item],
    categories: [{ id: 'BROAD_MARKET', count: 0, items: [] }, { id: 'SECTORAL', count: 1, items: [item] }, { id: 'THEMATIC', count: 0, items: [] }],
    activity: [{ eventId: 'event-1', activityType: 'QUADRANT', eventType: 'QUADRANT_ENTERED', effectiveDate: '2026-09-11', previousZone: null, newZone: 'LEADING', strength: 9, momentum: 3, index: { code: 'NIFTY IT', name: 'NIFTY IT' } }],
    methodology: 'Same detector pipeline.',
  })
})

describe('IndicesPage', () => {
  it('shows index evidence and switches to a persisted list view', async () => {
    const navigate = vi.fn()
    render(<IndicesPage onNavigate={navigate} onUnauthorized={vi.fn()} />)
    expect(await screen.findByRole('heading', { name: 'NIFTY IT' })).toBeTruthy()
    expect(screen.getByText('VCP-3C')).toBeTruthy()
    expect(screen.getByText('Entered Leading quadrant')).toBeTruthy()
    await userEvent.click(screen.getByRole('button', { name: 'List' }))
    expect(localStorage.getItem(INDEX_VIEW_STORAGE_KEY)).toBe('list')
    expect(navigate).toHaveBeenCalledWith('/indices?view=list')
  })

  it('plots indices in the quadrant and opens the index security view', async () => {
    localStorage.setItem(INDEX_VIEW_STORAGE_KEY, 'quadrant')
    const navigate = vi.fn()
    render(<IndicesPage onNavigate={navigate} onUnauthorized={vi.fn()} />)
    expect(await screen.findByText('5-session path')).toBeTruthy()
    expect(document.querySelectorAll('.watchlist-quadrant__trail')).toHaveLength(1)
    const point = await screen.findByRole('button', { name: /NIFTY IT: Leading/ })
    await userEvent.click(point)
    expect(navigate).toHaveBeenCalledWith('/indices/NIFTY%20IT')
  })
})

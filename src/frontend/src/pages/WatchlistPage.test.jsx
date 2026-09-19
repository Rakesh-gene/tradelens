import React from 'react'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import WatchlistPage from './WatchlistPage.jsx'
import { getWatchlist } from '../api/watchlistApi.js'
import { WATCHLIST_VIEW_STORAGE_KEY } from '../watchlistPreferences.js'

vi.mock('../api/watchlistApi.js', () => ({ getWatchlist: vi.fn(), removeFromWatchlist: vi.fn() }))

const watchlistItem = {
  security: { isin: 'INE002A01018', symbol: 'RELIANCE', name: 'Reliance Industries', sectorName: 'Energy' },
  dataAsOf: '2026-09-11', attentionGroup: 'NEAR_BREAKOUT', lastClose: 98, dailyChangePct: 2,
  distanceTo52WeekHighPct: -4, relativeStrength1m: 2, relativeStrength3m: 8,
  relativeStrength6m: 12, relativeStrength12m: 18, relativeStrengthPercentile: 92,
  trend: { aboveEma20: true, aboveSma50: true, aboveSma200: true },
  sectorContext: { relativeStrength: 5 }, rotation: { strength: 8, momentum: 1.5, zone: 'LEADING', trail: [
    { date: '2026-09-05', strength: 6, momentum: 0.5 }, { date: '2026-09-08', strength: 7, momentum: 1 },
    { date: '2026-09-09', strength: 8, momentum: 1.5 }, { date: '2026-09-10', strength: 8, momentum: 1.2 },
    { date: '2026-09-11', strength: 8, momentum: 1.5 },
  ] },
  primarySetup: { patternInstanceId: '00000000-0000-4000-8000-000000000001', patternType: 'BASE-VCP', variant: 'VCP-3C', state: 'READY', setupScore: 84, pivotPrice: 100, supportPrice: 92, invalidationPrice: 89, distanceToPivotPct: -2 },
}

beforeEach(() => {
  window.history.replaceState({}, '', '/watchlist')
  localStorage.clear()
  getWatchlist.mockReset()
  getWatchlist.mockResolvedValue({
    dataAsOf: '2026-09-11', count: 1, limit: 100, isStale: false,
    groups: [
      { id: 'ACTION_REQUIRED', count: 0, items: [] },
      { id: 'NEAR_BREAKOUT', count: 1, items: [watchlistItem] },
      { id: 'DEVELOPING', count: 0, items: [] }, { id: 'WEAKENING', count: 0, items: [] }, { id: 'NO_ACTIVE_SETUP', count: 0, items: [] },
    ],
    items: [watchlistItem],
    activity: [
      { eventId: 'event-2', activityType: 'QUADRANT', eventType: 'QUADRANT_CHANGED', effectiveDate: '2026-09-11', previousZone: 'IMPROVING', newZone: 'LEADING', strength: 8, momentum: 1.5, security: { isin: 'INE002A01018', symbol: 'RELIANCE' } },
      { eventId: 'event-1', activityType: 'PATTERN', patternInstanceId: '00000000-0000-4000-8000-000000000001', eventType: 'STATE_CHANGED', effectiveDate: '2026-09-11', previousState: 'MATURE', newState: 'READY', security: { isin: 'INE002A01018', symbol: 'RELIANCE' }, variant: 'VCP-3C' },
    ],
  })
})

describe('WatchlistPage', () => {
  it('renders server-owned action groups, enriched evidence and recent activity', async () => {
    render(<WatchlistPage onNavigate={vi.fn()} onUnauthorized={vi.fn()} />)

    expect(await screen.findByRole('heading', { name: 'Near breakout' })).toBeTruthy()
    expect(screen.getByText('₹98.00')).toBeTruthy()
    expect(screen.getByText('Sector RS')).toBeTruthy()
    expect(screen.getByRole('heading', { name: 'Recent activity' })).toBeTruthy()
    expect(screen.getByText(/MATURE → READY/)).toBeTruthy()
    expect(screen.getByText(/Improving → Leading/)).toBeTruthy()
  })

  it('reloads when the app reports a watchlist change', async () => {
    const view = render(<WatchlistPage onNavigate={vi.fn()} onUnauthorized={vi.fn()} revision={0} />)
    await waitFor(() => expect(getWatchlist).toHaveBeenCalledTimes(1))

    view.rerender(<WatchlistPage onNavigate={vi.fn()} onUnauthorized={vi.fn()} revision={1} />)

    await waitFor(() => expect(getWatchlist).toHaveBeenCalledTimes(2))
  })

  it('switches between card and compact list layouts through the URL', async () => {
    const navigate = vi.fn()
    const firstView = render(<WatchlistPage onNavigate={navigate} onUnauthorized={vi.fn()} />)
    await userEvent.click(await screen.findByRole('button', { name: /List/ }))
    expect(navigate).toHaveBeenCalledWith('/watchlist?view=list')
    expect(localStorage.getItem(WATCHLIST_VIEW_STORAGE_KEY)).toBe('list')

    firstView.unmount()
    window.history.replaceState({}, '', '/watchlist?view=list')
    render(<WatchlistPage onNavigate={vi.fn()} onUnauthorized={vi.fn()} />)
    expect((await screen.findByRole('button', { name: /List/ })).getAttribute('aria-pressed')).toBe('true')
    expect(screen.getByRole('button', { name: 'Remove RELIANCE from watchlist' })).toBeTruthy()
  })

  it('restores the saved layout when returning without a view query', async () => {
    localStorage.setItem(WATCHLIST_VIEW_STORAGE_KEY, 'quadrant')
    render(<WatchlistPage onNavigate={vi.fn()} onUnauthorized={vi.fn()} />)

    expect((await screen.findByRole('button', { name: /Quadrant/ })).getAttribute('aria-pressed')).toBe('true')
    expect(screen.getByRole('button', { name: /RELIANCE: Leading/ })).toBeTruthy()
  })

  it('shows each stock’s five-session path and keeps the latest point navigable', async () => {
    const navigate = vi.fn()
    window.history.replaceState({}, '', '/watchlist?view=quadrant')
    render(<WatchlistPage onNavigate={navigate} onUnauthorized={vi.fn()} />)

    expect((await screen.findByRole('button', { name: /Quadrant/ })).getAttribute('aria-pressed')).toBe('true')
    expect(document.querySelectorAll('.watchlist-quadrant__trail')).toHaveLength(1)
    expect(screen.getByText('5-session path')).toBeTruthy()
    const point = screen.getByRole('button', { name: /RELIANCE: Leading/ })
    await userEvent.click(point)
    expect(navigate).toHaveBeenCalledWith('/securities/RELIANCE')
  })
})

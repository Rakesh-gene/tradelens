import React from 'react'
import { render, screen, waitFor, cleanup } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import SectorRotation from './SectorRotation.jsx'
import { getSectorRotation, getSectorStocks } from '../api/marketApi.js'

vi.mock('../api/marketApi.js', () => ({ getSectorRotation: vi.fn(), getSectorStocks: vi.fn() }))
const sector = { code: 'TECH', name: 'Technology', zone: 'LEADING', rs3m: 12, momentum: 3, coveredCount: 5, memberCount: 6, pairedCount: 4, isPartial: true, trail: [
  { date: '2026-09-04', strength: 8, momentum: 1 }, { date: '2026-09-05', strength: 9, momentum: 1.5 },
  { date: '2026-09-08', strength: 10, momentum: 2 }, { date: '2026-09-09', strength: 11, momentum: 2.5 },
  { date: '2026-09-10', strength: 12, momentum: 3 },
] }
beforeEach(() => {
  window.history.replaceState({}, '', '/sector-rotation')
  getSectorRotation.mockResolvedValue({ dataAsOf: '2026-09-10', comparisonDate: '2026-08-13', items: [sector] })
  getSectorStocks.mockResolvedValue({ items: [{ rank: 1, rs3m: 22, security: { isin: 'INE002A01018', symbol: 'RELIANCE', name: 'Reliance Industries' } }], nextCursor: null })
})
afterEach(() => { cleanup(); vi.clearAllMocks() })

describe('Sector rotation', () => {
  it('supports quadrant selection with a shareable sector and date', async () => {
    const navigate = vi.fn()
    render(<SectorRotation onNavigate={navigate} />)
    await userEvent.click(await screen.findByRole('button', { name: /Technology: Leading/ }))
    expect(navigate).toHaveBeenCalledWith('/sector-rotation?sector=TECH&asOf=2026-09-10')
    expect(document.querySelectorAll('.watchlist-quadrant__trail')).toHaveLength(1)
    expect(screen.getByText(/5\/6 partial/)).toBeTruthy()
  })
  it('loads the selected sector and links ranked stocks to their fingerprint', async () => {
    window.history.replaceState({}, '', '/sector-rotation?sector=TECH&asOf=2026-09-10')
    render(<SectorRotation onNavigate={vi.fn()} />)
    expect((await screen.findByRole('link', { name: /RELIANCE/ })).getAttribute('href')).toBe('/securities/RELIANCE')
    expect(getSectorStocks.mock.calls[0][0]).toMatchObject({ sector: 'TECH', asOf: '2026-09-10' })
  })
  it('keeps missing-history sectors accessible outside the plot', async () => {
    getSectorRotation.mockResolvedValue({ items: [{ ...sector, momentum: null, zone: 'UNAVAILABLE' }] })
    render(<SectorRotation onNavigate={vi.fn()} />)
    expect(await screen.findByText(/No sectors have comparable history/)).toBeTruthy()
    expect(screen.getByRole('button', { name: /Technology.*Insufficient history/ })).toBeTruthy()
  })
  it('offers retry after API errors', async () => {
    getSectorRotation.mockRejectedValueOnce(new Error('Temporarily unavailable'))
    render(<SectorRotation onNavigate={vi.fn()} />)
    await userEvent.click(await screen.findByRole('button', { name: 'Try again' }))
    await waitFor(() => expect(screen.getByRole('button', { name: /Technology: Leading/ })).toBeTruthy())
  })
})

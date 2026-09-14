import React from 'react'
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import MarketRegimeCard from './MarketRegimeCard.jsx'

describe('MarketRegimeCard', () => {
  it('shows the NIFTY 50 chart and NIFTY 500 breadth without a second chart or oversized score', () => {
    const { container } = render(<MarketRegimeCard market={{
      label: 'DEFENSIVE', regimeScore: 0, aboveEma20Pct: 34.5,
      aboveSma50Pct: 36.6, aboveSma200Pct: 41.8, new52WeekHighs: 0,
      breakouts: 6, failedBreakouts: 3,
      indices: [
        { code: 'NIFTY 50', name: 'NIFTY 50', dataAsOf: '2026-09-11', lastClose: 25000, periodChangePct: 2.5, series: [{ date: '2026-09-10', close: 24000 }, { date: '2026-09-11', close: 25000 }] },
        { code: 'NIFTY 500', name: 'NIFTY 500', dataAsOf: '2026-09-11', lastClose: 23000, periodChangePct: -1, series: [{ date: '2026-09-10', close: 23200 }, { date: '2026-09-11', close: 23000 }] },
      ],
    }} />)

    expect(screen.getAllByRole('heading', { level: 3 }).map((heading) => heading.textContent)).toEqual(['NIFTY 50', 'NIFTY 500'])
    expect(screen.getByText('DEFENSIVE')).toBeTruthy()
    expect(screen.getByText('Above EMA20')).toBeTruthy()
    expect(container.querySelector('.regime-score')).toBeNull()
    expect(screen.getAllByRole('img')).toHaveLength(1)
    expect(container.querySelector('.market-index__area')).toBeTruthy()
  })
})

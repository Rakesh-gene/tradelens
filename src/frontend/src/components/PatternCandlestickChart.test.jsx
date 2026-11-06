import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import PatternCandlestickChart from './PatternCandlestickChart.jsx'

const { markers, attach, priceLine } = vi.hoisted(() => ({ markers: vi.fn(), attach: vi.fn(), priceLine: vi.fn() }))
vi.mock('lightweight-charts', () => ({
  CandlestickSeries: 'candles', HistogramSeries: 'volume', LineSeries: 'line', LineStyle: { Dashed: 2 },
  createSeriesMarkers: markers,
  createChart: () => ({ addSeries: () => ({ setData: vi.fn(), attachPrimitive: attach, createPriceLine: priceLine,
    priceScale: () => ({ applyOptions: vi.fn() }) }),
  timeScale: () => ({ fitContent: vi.fn() }), applyOptions: vi.fn(), remove: vi.fn() }),
}))
beforeAll(() => { globalThis.ResizeObserver = class { observe() {} disconnect() {} } })
beforeEach(() => { markers.mockClear(); attach.mockClear(); priceLine.mockClear() })
const candles = ['2026-10-01', '2026-10-02', '2026-10-05'].map((date) => ({ date, open: 100, high: 110, low: 95, close: 105 }))
const confirmed = { patternInstanceId: 'confirmed', patternType: 'BRK-RANGE', confirmationDate: '2026-10-05', state: 'CONFIRMED',
  shapes: [{ kind: 'line', label: 'Breakout resistance', points: [{ date: '2026-10-01', price: 101 }, { date: '2026-10-02', price: 101 }] }] }

describe('Confirmed pattern chart', () => {
  it('marks the recorded confirmation, not all daily detections, and attaches its geometry', () => {
    render(<PatternCandlestickChart candles={candles} levels={{ pivot: null }} evidence={[{ patternType: 'TREND-MA', detectedDate: '2026-10-01' }]}
      patternAnnotations={[confirmed]} />)
    expect(markers.mock.calls[0][1]).toEqual([expect.objectContaining({ time: '2026-10-05', text: 'Entry confirmed · BRK-RANGE' })])
    expect(attach).toHaveBeenCalledTimes(1)
    expect(priceLine).not.toHaveBeenCalled() // null is not a fabricated price of zero.
    expect(screen.queryByText('Recorded entry confirmations')).toBeNull()
    expect(screen.queryByText(/Every pattern found/)).toBeNull()
    expect(screen.queryByText('Pattern structure values')).toBeNull()
    expect(screen.queryByText('Open accessible price summary')).toBeNull()
    expect(screen.queryByRole('table')).toBeNull()
    expect(screen.getByRole('img').getAttribute('aria-label')).toContain('Entry confirmed')
  })

  it('shows selected unconfirmed geometry without inventing entry confirmation', () => {
    render(<PatternCandlestickChart candles={candles} selectedPatternId="ready" patternAnnotations={[
      confirmed, { ...confirmed, patternInstanceId: 'ready', confirmationDate: null, state: 'READY' },
    ]} />)
    expect(markers).not.toHaveBeenCalled()
    expect(attach).toHaveBeenCalledTimes(1)
    expect(screen.getByRole('img').getAttribute('aria-label')).toContain('No recorded entry confirmation')
  })

  it('groups confirmations on the same session into one marker', () => {
    render(<PatternCandlestickChart candles={candles} patternAnnotations={[confirmed, { ...confirmed, patternInstanceId: 'second' }]} />)
    expect(markers.mock.calls[0][1]).toHaveLength(1)
    expect(markers.mock.calls[0][1][0].text).toBe('Entry confirmed · 2 setups')
  })

  it('does not infer confirmation from state or detection alone', () => {
    render(<PatternCandlestickChart candles={candles} selectedPatternId="legacy" evidence={[
      { patternInstanceId: 'legacy', state: 'CONFIRMED', detectedDate: '2026-10-02' },
    ]} />)
    expect(markers).not.toHaveBeenCalled()
    expect(attach).not.toHaveBeenCalled()
    expect(screen.getByRole('img')).toBeTruthy()
  })
})

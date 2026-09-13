import { describe, expect, it } from 'vitest'
import { groupPatternDetections, patternChartGeometry } from './patternChartOverlays.js'

const rows = [
  { time: '2026-01-02', high: 110, low: 100 },
  { time: '2026-01-09', high: 104, low: 90 },
  { time: '2026-01-16', high: 109, low: 99 },
  { time: '2026-01-23', high: 105, low: 92 },
]

describe('patternChartGeometry', () => {
  it('draws double-top pivots through the neckline', () => {
    const geometry = patternChartGeometry({ patternType: 'REV-DTOP', measurements: {
      first_pivot_date: '2026-01-02', neckline_pivot_date: '2026-01-09', second_pivot_date: '2026-01-16',
    } }, rows)

    expect(geometry.points).toEqual([
      { time: '2026-01-02', value: 110, label: 'Top 1' },
      { time: '2026-01-09', value: 90, label: 'Neckline' },
      { time: '2026-01-16', value: 109, label: 'Top 2' },
    ])
  })

  it('draws bullish AB=CD using alternating highs and lows', () => {
    const geometry = patternChartGeometry({ patternType: 'HARM-ABCD', direction: 'BULLISH', measurements: {
      a_date: '2026-01-02', b_date: '2026-01-09', c_date: '2026-01-16', d_date: '2026-01-23',
    } }, rows)

    expect(geometry.points.map(({ value, label }) => [label, value])).toEqual([
      ['A', 110], ['B', 90], ['C', 109], ['D', 92],
    ])
  })

  it('groups every pattern by its detected date inside the visible chart range', () => {
    const groups = groupPatternDetections([
      { patternInstanceId: 'one', detectedDate: '2026-01-09' },
      { patternInstanceId: 'two', detectedDate: '2026-01-09' },
      { patternInstanceId: 'outside', detectedDate: '2025-12-01' },
    ], rows)

    expect(groups).toHaveLength(1)
    expect(groups[0].time).toBe('2026-01-09')
    expect(groups[0].patterns.map((item) => item.patternInstanceId)).toEqual(['one', 'two'])
  })
})

import { describe, expect, it, vi } from 'vitest'
import PatternShapePrimitive from './patternShapePrimitive.js'

describe('Pattern shape primitive', () => {
  it('draws server boxes/lines and updates coordinates when the chart moves', () => {
    let offset = 0
    const primitive = new PatternShapePrimitive([
      { kind: 'box', startDate: 'start', endDate: 'end', upperPrice: 110, lowerPrice: 90 },
      { kind: 'line', points: [{ date: 'start', price: 100 }, { date: 'end', price: 105 }] },
    ])
    primitive.attached({ chart: { timeScale: () => ({ timeToCoordinate: (date) => (date === 'start' ? 10 : 30) + offset }) },
      series: { priceToCoordinate: (price) => 200 - price }, requestUpdate: vi.fn() })
    const context = Object.fromEntries(['save', 'restore', 'fillRect', 'strokeRect', 'beginPath', 'moveTo', 'lineTo', 'stroke'].map((name) => [name, vi.fn()]))
    const target = { useMediaCoordinateSpace: (draw) => draw({ context }) }
    primitive.updateAllViews(); primitive.draw(target)
    expect(context.strokeRect).toHaveBeenLastCalledWith(10, 90, 20, 20)
    expect(context.lineTo).toHaveBeenLastCalledWith(30, 95)
    offset = 5
    primitive.updateAllViews(); primitive.draw(target)
    expect(context.strokeRect).toHaveBeenLastCalledWith(15, 90, 20, 20)
    primitive.detached()
    expect(primitive.paths).toEqual([])
  })
})

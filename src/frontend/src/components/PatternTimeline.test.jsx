import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import PatternTimeline from './PatternTimeline.jsx'

describe('PatternTimeline', () => {
  it('shows effective state history without internal technical changes', () => {
    render(<PatternTimeline events={[{ eventId: 'e1', eventType: 'STATE_CHANGED', effectiveDate: '2026-09-04', recordedAt: '2026-09-04T13:15:00Z', previousState: 'MATURE', newState: 'READY', changes: { pivot: 500 } }]} />)
    expect(screen.getByText('MATURE → READY')).toBeTruthy()
    expect(screen.queryByText('Technical changes')).toBeNull()
    expect(screen.queryByText(/"pivot": 500/)).toBeNull()
  })
})

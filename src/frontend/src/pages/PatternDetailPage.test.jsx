import { render, screen } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import PatternDetailPage from './PatternDetailPage.jsx'
import { getPattern, getPatternEvents, getPatternChart } from '../api/patternApi.js'

vi.mock('../api/patternApi.js', () => ({ getPattern: vi.fn(), getPatternEvents: vi.fn(), getPatternChart: vi.fn() }))
vi.mock('../components/PatternCandlestickChart.jsx', () => ({ default: () => <div>Setup chart</div> }))

beforeEach(() => {
  getPattern.mockResolvedValue({
    dataAsOf: '2026-09-11', latestDataAsOf: '2026-10-19', hasNewerData: true, isStale: true,
    pattern: {
      patternInstanceId: 'old-setup', security: { symbol: 'SETL', name: 'Standard Engineering Technology Limited' },
      patternType: 'BRK-ATH', state: 'CONFIRMED', lastUpdatedDate: '2026-09-11',
      decision: { headline: 'Entry confirmed', confidenceBand: 'MODERATE', confidenceScore: 72,
        nextStep: 'Hold only while the setup remains valid.', summary: 'Repeated setup explanation.',
        levels: { triggerPrice: 100, invalidationPrice: 90, riskFromTriggerPct: 10 } },
      allEvidence: [], measurements: {}, scoreComponents: { context: {}, setup: {} }, lineage: {},
    },
  })
  getPatternEvents.mockResolvedValue({ items: [] })
  getPatternChart.mockResolvedValue({ candles: [], levels: {} })
})

it('distinguishes the old setup snapshot and links to current symbol analysis', async () => {
  render(<PatternDetailPage patternId="old-setup" onNavigate={vi.fn()} />)
  const notice = await screen.findByLabelText('Setup data freshness')
  expect(notice.textContent).toContain('19 Oct 2026')
  expect(screen.getByText('Setup evidence as of')).toBeTruthy()
  expect(screen.getByText('11 Sept 2026')).toBeTruthy()
  expect(screen.getByRole('link', { name: /Latest SETL chart/ }).getAttribute('href')).toBe('/securities/SETL')
  expect(notice.tagName).toBe('FOOTER')
  expect(notice.parentElement.lastElementChild).toBe(notice)
  expect(screen.queryByText(/This page shows the evidence for this specific setup/)).toBeNull()
  const chart = screen.getByText('Setup chart').closest('section')
  const decision = screen.getByRole('heading', { name: 'Decision intelligence' }).closest('section')
  expect(chart.nextElementSibling).toBe(decision)
  expect(screen.getAllByText('Trigger', { exact: true })).toHaveLength(1)
  expect(screen.queryByText('Trigger level')).toBeNull()
  expect(screen.queryByText('Repeated setup explanation.')).toBeNull()
  expect(screen.queryByText('Learn from history')).toBeNull()
  expect(screen.queryByRole('heading', { name: 'Similar case studies' })).toBeNull()
  expect(screen.queryByText('Detailed evidence, scores and lifecycle')).toBeNull()
  expect(screen.queryByText(/^Engine |^Configuration |^Features |^Adjustments /)).toBeNull()
  expect(getPatternEvents).not.toHaveBeenCalled()
})

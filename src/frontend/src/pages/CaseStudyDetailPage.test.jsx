import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import CaseStudyDetailPage from './CaseStudyDetailPage.jsx'
import { getCaseStudy, getCaseStudyChart } from '../api/caseStudyApi.js'

vi.mock('../api/caseStudyApi.js', () => ({ getCaseStudy: vi.fn(), getCaseStudyChart: vi.fn() }))
vi.mock('../components/PatternCandlestickChart.jsx', () => ({ default: ({ milestones }) => <div data-testid="case-chart">Chart with {milestones.length} milestones</div> }))

describe('CaseStudyDetailPage', () => {
  beforeEach(() => {
    getCaseStudy.mockResolvedValue({ caseStudy: {
      caseStudyId: '00000000-0000-0000-0000-000000000777', isin: 'INE002A01018', symbol: 'RELIANCE', patternType: 'BASE-VCP', state: 'TRIGGERED', detectionDate: '2025-01-02', entryDate: '2025-01-03', entryPrice: 100, setupScore: 80,
      prices: { pivotPrice: 101, supportPrice: 95, invalidationPrice: 94 }, entryRationale: { summary: 'The pattern qualified.', reasons: ['Compression and breakout aligned.'], cautions: [], entryRule: 'Start after the EOD signal.' },
      positionalPerformance: { entryDate: '2025-01-03', entryPrice: 100, horizons: { '3M': { targetSessions: 63, availableSessions: 63, complete: true, observationDate: '2025-04-03', closePrice: 110, returnPct: 10, maxAdvancePct: 14, maxDrawdownPct: -4 }, '6M': { targetSessions: 126, availableSessions: 126, complete: true, observationDate: '2025-07-03', closePrice: 120, returnPct: 20, maxAdvancePct: 25, maxDrawdownPct: -4 }, '1Y': { targetSessions: 252, availableSessions: 252, complete: true, observationDate: '2026-01-03', closePrice: 130, returnPct: 30, maxAdvancePct: 35, maxDrawdownPct: -6 } } },
      measurements: {}, supportingEvidence: [], context: {}, lineage: {},
    }, dataAsOf: '2026-01-03' })
    getCaseStudyChart.mockResolvedValue({ candles: [], levels: {}, evidence: [], milestones: [{ label: '3M' }, { label: '6M' }, { label: '1Y' }] })
  })

  it('centers the chart, entry rationale, and positional horizons instead of profit', async () => {
    render(<CaseStudyDetailPage caseStudyId="00000000-0000-0000-0000-000000000777" onNavigate={() => {}} onUnauthorized={() => {}} />)
    expect((await screen.findByTestId('case-chart')).textContent).toContain('3 milestones')
    expect(screen.getByRole('heading', { name: 'What is a volatility contraction pattern?' })).not.toBeNull()
    expect(screen.getByText(/available supply is being absorbed/)).not.toBeNull()
    expect(screen.getByRole('heading', { name: 'What qualified at the time' })).not.toBeNull()
    expect(screen.getByRole('heading', { name: 'How the stock performed after entry' })).not.toBeNull()
    expect(screen.getByText('+30%')).not.toBeNull()
    expect(screen.queryByRole('heading', { name: 'Pattern evidence available at detection' })).toBeNull()
    expect(screen.queryByText(/Gross.*P\/L/)).toBeNull()
  })
})

import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import CaseStudiesPage from './CaseStudiesPage.jsx'
import { getCaseStudies } from '../api/caseStudyApi.js'

vi.mock('../api/caseStudyApi.js', () => ({ getCaseStudies: vi.fn() }))

describe('CaseStudiesPage', () => {
  beforeEach(() => {
    window.history.replaceState({}, '', '/case-studies')
    getCaseStudies.mockReset()
    getCaseStudies.mockResolvedValue({
      dataAsOf: '2026-09-11', nextCursor: null,
      items: [{
        caseStudyId: '00000000-0000-0000-0000-000000000777', isin: 'INE002A01018', symbol: 'RELIANCE', companyName: 'Reliance Industries Limited',
        patternType: 'REV-DBOT', timeframe: '1D', state: 'TRIGGERED', detectionDate: '2025-01-02', entryDate: '2025-01-03', entryPrice: 100,
        positionalPerformance: { horizons: { '3M': { complete: true, returnPct: 10 }, '6M': { complete: false }, '1Y': { complete: false } } },
      }],
    })
  })

  it('shows a browse-only tile/list catalog with clickable cases', async () => {
    const onNavigate = vi.fn()
    render(<CaseStudiesPage onNavigate={onNavigate} onUnauthorized={() => {}} />)
    expect(await screen.findByRole('heading', { name: 'RELIANCE' })).not.toBeNull()
    expect(screen.queryByLabelText('Case-study filters')).toBeNull()
    expect(screen.getByText('double bottom')).not.toBeNull()
    expect(screen.getByRole('link', { name: /Open case study/ }).getAttribute('href')).toContain('/case-studies/00000000')
    await userEvent.click(screen.getByRole('button', { name: 'List' }))
    expect(onNavigate).toHaveBeenCalledWith('/case-studies?view=list', { replace: true })
  })
})

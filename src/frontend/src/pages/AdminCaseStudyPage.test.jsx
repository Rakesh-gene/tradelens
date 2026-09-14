import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import AdminCaseStudyPage from './AdminCaseStudyPage.jsx'
import { createCaseStudyRun, getCaseStudyReviewQueue, reviewCaseStudy } from '../api/adminApi.js'
import { searchSecurities } from '../api/securityApi.js'

vi.mock('../api/adminApi.js', () => ({
  createCaseStudyRun: vi.fn(), getCaseStudyReviewQueue: vi.fn(), getCaseStudyRun: vi.fn(), getCaseStudyRunItems: vi.fn(), resumeCaseStudyRun: vi.fn(), reviewCaseStudy: vi.fn(),
}))
vi.mock('../api/securityApi.js', () => ({ searchSecurities: vi.fn() }))

describe('AdminCaseStudyPage', () => {
  beforeEach(() => {
    createCaseStudyRun.mockReset()
    getCaseStudyReviewQueue.mockReset()
    reviewCaseStudy.mockReset()
    searchSecurities.mockReset()
    searchSecurities.mockResolvedValue({ items: [{ isin: 'INE002A01018', symbol: 'RELIANCE', name: 'Reliance Industries Limited' }] })
    createCaseStudyRun.mockResolvedValue({ run: { runId: '00000000-0000-0000-0000-000000000123', status: 'COMPLETED', stock: { isin: 'INE002A01018', symbol: 'RELIANCE' }, lookback: '5Y', fromDate: '2021-09-12', toDate: '2026-09-12', casesRecorded: 0, caseStudyIds: [] } })
    getCaseStudyReviewQueue.mockResolvedValue({ items: [] })
    reviewCaseStudy.mockResolvedValue({ caseStudy: {} })
  })

  it('submits only the selected stock and date range', async () => {
    render(<AdminCaseStudyPage onNavigate={() => {}} onUnauthorized={() => {}} />)
    expect(screen.getAllByRole('combobox')).toHaveLength(2)
    expect(screen.getByRole('combobox', { name: 'Date range' }).classList.contains('select-control')).toBe(true)
    await userEvent.type(screen.getByRole('combobox', { name: 'Stock' }), 'rel')
    await userEvent.click(await screen.findByRole('option', { name: /RELIANCE/ }, { timeout: 1000 }))
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Date range' }), '5Y')
    await userEvent.click(screen.getByRole('button', { name: 'Build case study' }))
    await waitFor(() => expect(createCaseStudyRun).toHaveBeenCalledWith({ isin: 'INE002A01018', lookback: '5Y' }, expect.any(Object)))
  })

  it('shows completed cases in the review queue and publishes them', async () => {
    getCaseStudyReviewQueue.mockResolvedValue({ items: [{ caseStudyId: '00000000-0000-0000-0000-000000000777', isin: 'INE002A01018', symbol: 'RELIANCE', patternType: 'BASE-VCP', timeframe: '1D', detectionDate: '2025-01-02', netPnl: 2000, netRMultiple: 2 }] })
    render(<AdminCaseStudyPage onNavigate={() => {}} onUnauthorized={() => {}} />)
    const publish = await screen.findByRole('button', { name: 'Publish reviewed case' })
    await userEvent.click(publish)
    expect(reviewCaseStudy).toHaveBeenCalledWith('00000000-0000-0000-0000-000000000777', 'REVIEWED', expect.any(Object))
  })
})

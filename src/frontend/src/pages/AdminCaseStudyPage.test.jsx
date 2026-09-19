import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import AdminCaseStudyPage from './AdminCaseStudyPage.jsx'
import { createCaseStudyRun, deleteCaseStudy, getCaseStudyReviewQueue, getCaseStudyRun, getCaseStudyRunItems, getLatestCaseStudyRun, reviewCaseStudy } from '../api/adminApi.js'
import { searchSecurities } from '../api/securityApi.js'

vi.mock('../api/adminApi.js', () => ({
  createCaseStudyRun: vi.fn(), deleteCaseStudy: vi.fn(), getCaseStudyReviewQueue: vi.fn(), getCaseStudyRun: vi.fn(), getCaseStudyRunItems: vi.fn(), getLatestCaseStudyRun: vi.fn(), resumeCaseStudyRun: vi.fn(), reviewCaseStudy: vi.fn(),
}))
vi.mock('../api/securityApi.js', () => ({ searchSecurities: vi.fn() }))

describe('AdminCaseStudyPage', () => {
  beforeEach(() => {
    window.sessionStorage.removeItem('tradelensCaseStudyRunId')
    createCaseStudyRun.mockReset()
    getCaseStudyRun.mockReset()
    getCaseStudyRunItems.mockReset()
    getLatestCaseStudyRun.mockReset()
    getCaseStudyReviewQueue.mockReset()
    reviewCaseStudy.mockReset()
    deleteCaseStudy.mockReset()
    searchSecurities.mockReset()
    searchSecurities.mockResolvedValue({ items: [{ isin: 'INE002A01018', symbol: 'RELIANCE', name: 'Reliance Industries Limited' }] })
    createCaseStudyRun.mockResolvedValue({ run: { runId: '00000000-0000-0000-0000-000000000123', status: 'COMPLETED', stock: { isin: 'INE002A01018', symbol: 'RELIANCE' }, lookback: '5Y', fromDate: '2021-09-12', toDate: '2026-09-12', casesRecorded: 0, caseStudyIds: [] } })
    getCaseStudyReviewQueue.mockResolvedValue({ items: [] })
    getCaseStudyRun.mockResolvedValue({ run: { runId: '00000000-0000-0000-0000-000000000123', status: 'RUNNING', stage: 'REPLAYING_HISTORY', progressPct: 35, sessionsProcessed: 250, lastCompletedSession: '2025-01-02', stock: { symbol: 'RELIANCE', isin: 'INE002A01018' } } })
    getCaseStudyRunItems.mockResolvedValue({ items: [] })
    getLatestCaseStudyRun.mockResolvedValue({ run: null })
    reviewCaseStudy.mockResolvedValue({ caseStudy: {} })
    deleteCaseStudy.mockResolvedValue({ deletedCaseStudyId: '00000000-0000-0000-0000-000000000777' })
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

  it('prevents publishing a pattern that is absent from the Setups dropdown', async () => {
    getCaseStudyReviewQueue.mockResolvedValue({ items: [{ caseStudyId: '00000000-0000-0000-0000-000000000777', isin: 'INE002A01018', symbol: 'RELIANCE', patternType: 'REV-DBOT', timeframe: '1D', detectionDate: '2025-01-02' }] })
    render(<AdminCaseStudyPage onNavigate={() => {}} onUnauthorized={() => {}} />)
    expect(await screen.findByText(/not available on the Setups page/)).not.toBeNull()
    expect(screen.getByRole('button', { name: 'Publish reviewed case' }).disabled).toBe(true)
    expect(screen.getByRole('button', { name: 'Delete case study' }).disabled).toBe(false)
  })

  it('bulk deletes selected cases after themed confirmation', async () => {
    getCaseStudyReviewQueue.mockResolvedValue({ items: [
      { caseStudyId: '00000000-0000-0000-0000-000000000777', isin: 'INE002A01018', symbol: 'RELIANCE', patternType: 'BASE-VCP', timeframe: '1D', detectionDate: '2025-01-02' },
      { caseStudyId: '00000000-0000-0000-0000-000000000778', isin: 'INE002A01018', symbol: 'RELIANCE', patternType: 'BASE-FLAT', timeframe: '1D', detectionDate: '2025-01-03' },
    ] })
    render(<AdminCaseStudyPage onNavigate={() => {}} onUnauthorized={() => {}} />)
    await screen.findByText(/BASE-FLAT/)
    await userEvent.click(screen.getByRole('checkbox', { name: 'Select all cases' }))
    await userEvent.click(screen.getByRole('button', { name: 'Delete selected (2)' }))
    expect(screen.getByRole('dialog', { name: 'Delete 2 case studies?' })).not.toBeNull()
    await userEvent.click(screen.getByRole('button', { name: 'Delete 2 cases' }))
    await waitFor(() => expect(deleteCaseStudy).toHaveBeenCalledTimes(2))
    expect(deleteCaseStudy).toHaveBeenCalledWith('00000000-0000-0000-0000-000000000777', expect.any(Object))
    expect(deleteCaseStudy).toHaveBeenCalledWith('00000000-0000-0000-0000-000000000778', expect.any(Object))
  })

  it('shows persisted running progress after returning to the page', async () => {
    window.sessionStorage.setItem('tradelensCaseStudyRunId', '00000000-0000-0000-0000-000000000123')
    render(<AdminCaseStudyPage onNavigate={() => {}} onUnauthorized={() => {}} />)
    expect(await screen.findByText('Checking historical setups')).not.toBeNull()
    expect(screen.getByText('About 35%')).not.toBeNull()
    expect(screen.getByRole('progressbar', { name: 'Estimated case-study build progress' }).value).toBe(35)
    expect(screen.getByText(/250 trading sessions checked/)).not.toBeNull()
  })

  it('restores completed run results and its review queue', async () => {
    window.sessionStorage.setItem('tradelensCaseStudyRunId', '00000000-0000-0000-0000-000000000123')
    getCaseStudyRun.mockResolvedValue({ run: { runId: '00000000-0000-0000-0000-000000000123', status: 'COMPLETED', stage: 'COMPLETED', progressPct: 100, stock: { symbol: 'RELIANCE', isin: 'INE002A01018' }, lookback: '1Y', casesRecorded: 1, caseStudyIds: ['00000000-0000-0000-0000-000000000777'] } })
    getCaseStudyReviewQueue.mockResolvedValue({ items: [{ caseStudyId: '00000000-0000-0000-0000-000000000777', isin: 'INE002A01018', symbol: 'RELIANCE', patternType: 'BASE-VCP', timeframe: '1D', detectionDate: '2025-01-02' }] })
    render(<AdminCaseStudyPage onNavigate={() => {}} onUnauthorized={() => {}} />)
    expect(await screen.findByRole('button', { name: 'Inspect case 1' })).not.toBeNull()
    expect(await screen.findByRole('button', { name: 'Publish reviewed case' })).not.toBeNull()
    expect(screen.getByText('1 case studies created.')).not.toBeNull()
  })

  it('finds the last build when the page is opened in a new session', async () => {
    getLatestCaseStudyRun.mockResolvedValue({ run: { runId: '00000000-0000-0000-0000-000000000123', status: 'COMPLETED', stage: 'COMPLETED', stock: { symbol: 'RELIANCE', isin: 'INE002A01018' }, lookback: '5Y', casesRecorded: 0, caseStudyIds: [] } })
    render(<AdminCaseStudyPage onNavigate={() => {}} onUnauthorized={() => {}} />)
    expect(await screen.findByText('Build complete')).not.toBeNull()
    expect(screen.getByRole('button', { name: 'Build again' })).not.toBeNull()
    expect(window.sessionStorage.getItem('tradelensCaseStudyRunId')).toBe('00000000-0000-0000-0000-000000000123')
  })
})

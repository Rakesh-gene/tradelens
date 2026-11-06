import React from 'react'
import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import OverviewPage from './OverviewPage.jsx'
import { getOverview } from '../api/marketApi.js'

vi.mock('../api/marketApi.js', () => ({ getOverview: vi.fn() }))
vi.mock('../components/MarketRegimeCard.jsx', () => ({ default: () => <div>Market</div> }))
vi.mock('../components/PatternUi.jsx', () => ({
  PageIntro: ({ title }) => <h1>{title}</h1>,
  SetupCard: ({ setup }) => <article>{setup.patternInstanceId}</article>,
}))
const qualification = { configurationVersion: 'policy-v1', qualifiedCount: 13, summary: 'Top 20% within each lifecycle state; all qualification checks pass.' }
const setup = (index) => ({ patternInstanceId: `setup-${index}`, state: 'READY', decision: { missingEvidence: ['relative-strength percentile'], cautions: ['Price is extended above the pivot'] }, overviewQualification: {
  policyVersion: 'overview-qualified-v1', evaluationDate: '2026-10-30', values: { bestFit: 75, peerPercentile: 90, quality: 80, context: 50, liquidity: 100 },
} })
const firstPage = () => ({ dataAsOf: '2026-10-30', countsByState: {}, market: {}, qualification, topSetups: Array.from({ length: 6 }, (_, index) => setup(index + 1)), nextCursor: 'opaque-page-2' })

describe('Overview setup pagination', () => {
  beforeEach(() => getOverview.mockReset())

  it('appends every page in server order and hides Load more at the end', async () => {
    getOverview.mockResolvedValueOnce(firstPage())
      .mockResolvedValueOnce({ qualification, topSetups: Array.from({ length: 6 }, (_, index) => setup(index + 7)), nextCursor: 'opaque-page-3' })
      .mockResolvedValueOnce({ qualification, topSetups: [setup(13)], nextCursor: null })
    render(<OverviewPage onNavigate={vi.fn()} />)
    await screen.findByText('Showing 6 of 13 qualified setups')
    expect(screen.queryByText(/Top 20% within each lifecycle state/)).toBeNull()
    expect(screen.queryByText('Why it qualifies')).toBeNull()
    expect(screen.queryByText(/Incomplete evidence:/)).toBeNull()
    expect(screen.getAllByText(/Caution: Price is extended/)).toHaveLength(6)
    await userEvent.click(screen.getByRole('button', { name: 'Load more' }))
    await screen.findByText('Showing 12 of 13 qualified setups')
    expect(getOverview.mock.calls[1][0]).toEqual({ top: 6, asOf: '2026-10-30', cursor: 'opaque-page-2' })
    await userEvent.click(screen.getByRole('button', { name: 'Load more' }))
    await screen.findByText('Showing 13 of 13 qualified setups')
    expect(screen.getAllByRole('article').map((item) => item.textContent)).toEqual(Array.from({ length: 13 }, (_, index) => `setup-${index + 1}`))
    expect(screen.queryByRole('button', { name: 'Load more' })).toBeNull()
  })

  it('preserves cards after failure and retries the same cursor without duplicates', async () => {
    getOverview.mockResolvedValueOnce(firstPage()).mockRejectedValueOnce(new Error('Temporarily unavailable'))
      .mockResolvedValueOnce({ qualification, topSetups: [setup(6), setup(7)], nextCursor: null })
    render(<OverviewPage onNavigate={vi.fn()} />)
    await userEvent.click(await screen.findByRole('button', { name: 'Load more' }))
    expect(await screen.findByRole('alert')).toHaveProperty('textContent', 'Temporarily unavailable')
    expect(screen.getAllByRole('article')).toHaveLength(6)
    await userEvent.click(screen.getByRole('button', { name: 'Retry load more' }))
    await screen.findByText('Showing 7 of 13 qualified setups')
    expect(getOverview.mock.calls[2][0].cursor).toBe('opaque-page-2')
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('blocks duplicate requests and aborts load more on unmount', async () => {
    getOverview.mockResolvedValueOnce(firstPage()).mockImplementationOnce(() => new Promise(() => {}))
    const view = render(<OverviewPage onNavigate={vi.fn()} />)
    const button = await screen.findByRole('button', { name: 'Load more' })
    fireEvent.click(button); fireEvent.click(button)
    expect(getOverview).toHaveBeenCalledTimes(2)
    expect(button.disabled).toBe(true)
    const signal = getOverview.mock.calls[1][1].signal
    view.unmount()
    expect(signal.aborted).toBe(true)
  })

  it('shows an empty state without pagination when no setups exist', async () => {
    getOverview.mockResolvedValue({ ...firstPage(), topSetups: [], nextCursor: null })
    render(<OverviewPage onNavigate={vi.fn()} />)
    expect(await screen.findByText('No qualifying setups')).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Load more' })).toBeNull()
  })

  it('does not label results from an older backend as qualified', async () => {
    getOverview.mockResolvedValue({ ...firstPage(), qualification: undefined })
    render(<OverviewPage onNavigate={vi.fn()} />)
    expect(await screen.findByRole('alert')).toHaveProperty('textContent', expect.stringContaining('Restart the backend'))
    expect(screen.queryByRole('article')).toBeNull()
  })

  it('does not mix pages from different policy configurations', async () => {
    getOverview.mockResolvedValueOnce(firstPage()).mockResolvedValueOnce({ qualification: { ...qualification, configurationVersion: 'policy-v2' }, topSetups: [setup(7)], nextCursor: null })
    render(<OverviewPage onNavigate={vi.fn()} />)
    await userEvent.click(await screen.findByRole('button', { name: 'Load more' }))
    expect(await screen.findByRole('alert')).toHaveProperty('textContent', 'Qualification rules changed. Refresh Overview before loading more setups.')
    expect(screen.getAllByRole('article')).toHaveLength(6)
  })
})

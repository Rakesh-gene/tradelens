import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import SetupTable from './SetupTable.jsx'

const setup = { patternInstanceId: '2a9ca55f-3d2d-4b25-b683-36979029fb97', security: { isin: 'INE002A01018', symbol: 'RELIANCE', name: 'Reliance Industries Limited', sectorName: 'Energy' }, patternClass: 'BASE', patternType: 'BASE-VCP', variant: 'VCP-3C', state: 'READY', setupScore: 89, qualityScore: 92, maturityScore: 88, pivotPrice: 1500, distanceToPivotPct: -1.7, detectedDate: '2026-09-04', bestFit: { score: 91, tier: 'LEADING', rankWithinState: 2, stateCandidateCount: 211 }, decision: { actionLabel: 'Ready', tone: 'action', confidenceBand: 'HIGH', confidenceScore: 90, headline: 'Ready — high-quality three-contraction VCP' } }

describe('SetupTable', () => {
  it('renders core evidence and a copyable detail URL', () => {
    render(<SetupTable items={[setup]} filters={{ sort: 'setupScore', direction: 'desc' }} onSort={() => {}} onNavigate={() => {}} />)
    expect(screen.getByRole('rowheader', { name: /RELIANCE/ })).toBeTruthy()
    expect(screen.getByText('VCP-3C')).toBeTruthy()
    expect(screen.getByText('Ready')).toBeTruthy()
    expect(screen.getByText(/Ready — high-quality three-contraction VCP/)).toBeTruthy()
    expect(screen.getByText(/LEADING/)).toBeTruthy()
    expect(screen.getByText(/#2 of 211/)).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Evidence' }).getAttribute('href')).toContain(setup.patternInstanceId)
  })

  it('delegates sorting to the server-backed page state', async () => {
    const sort = vi.fn()
    render(<SetupTable items={[setup]} filters={{ sort: 'setupScore', direction: 'desc' }} onSort={sort} onNavigate={() => {}} />)
    await userEvent.click(screen.getByRole('button', { name: /Sort by Quality/ }))
    expect(sort).toHaveBeenCalledWith('qualityScore')
  })

  it('delegates best-fit sorting to the server', async () => {
    const sort = vi.fn()
    render(<SetupTable items={[setup]} filters={{ sort: 'setupScore', direction: 'desc' }} onSort={sort} onNavigate={() => {}} />)
    await userEvent.click(screen.getByRole('button', { name: /Sort by Best fit/ }))
    expect(sort).toHaveBeenCalledWith('bestFit')
  })
})

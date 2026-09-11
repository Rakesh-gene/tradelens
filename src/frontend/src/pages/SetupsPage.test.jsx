import React from 'react'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import SetupsPage from './SetupsPage.jsx'
import { getSetups } from '../api/marketApi.js'

const setup = (number) => ({ patternInstanceId: `pattern-${number}` })
const { initialPage } = vi.hoisted(() => ({
  initialPage: {
    dataAsOf: '2026-09-10',
    items: Array.from({ length: 25 }, (_, index) => ({ patternInstanceId: `pattern-${index + 1}` })),
    nextCursor: 'cursor-25',
    totalCount: 60,
    facets: {},
  },
}))

vi.mock('../api/marketApi.js', () => ({ getSetups: vi.fn() }))
vi.mock('../useApiResource.js', () => ({
  default: () => ({
    data: initialPage,
    error: null,
    status: 'success',
    reload: vi.fn(),
  }),
}))
vi.mock('../hooks/useMediaQuery.js', () => ({ default: () => false }))
vi.mock('../hooks/useDocumentTitle.js', () => ({ default: () => {} }))
vi.mock('../components/PatternFilters.jsx', () => ({ default: () => <div>Filters</div> }))
vi.mock('../components/PatternUi.jsx', () => ({
  PageIntro: ({ title }) => <h1>{title}</h1>,
  SetupCard: ({ setup: item }) => <article>{item.patternInstanceId}</article>,
}))
vi.mock('../components/ResourceStates.jsx', () => ({
  EmptyState: () => <div>No setups</div>,
  ResourceState: ({ children }) => children,
}))

describe('SetupsPage', () => {
  beforeEach(() => {
    window.history.replaceState({}, '', '/setups')
    getSetups.mockReset()
  })

  it('starts with 25 tiles and appends the next 25 with an exact remaining count', async () => {
    getSetups.mockResolvedValue({
      items: Array.from({ length: 25 }, (_, index) => setup(index + 26)),
      nextCursor: 'cursor-50',
      totalCount: 60,
    })
    render(<SetupsPage onNavigate={vi.fn()} onUnauthorized={vi.fn()} />)

    expect(await screen.findByText('Showing 25 of 60 securities · sorted highest first by setupScore')).toBeTruthy()
    expect(screen.getByText('35 remaining')).toBeTruthy()

    await userEvent.click(screen.getByRole('button', { name: 'Show 25 more' }))

    await waitFor(() => expect(screen.getByText('Showing 50 of 60 securities · sorted highest first by setupScore')).toBeTruthy())
    expect(screen.getByText('10 remaining')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Show 10 more' })).toBeTruthy()
    expect(screen.getByText('pattern-50')).toBeTruthy()
    expect(getSetups).toHaveBeenCalledWith(
      expect.objectContaining({ cursor: 'cursor-25', pageSize: 25 }),
      expect.objectContaining({ onUnauthorized: expect.any(Function) }),
    )
  })
})

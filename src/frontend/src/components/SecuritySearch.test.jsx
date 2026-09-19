import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import SecuritySearch from './SecuritySearch.jsx'
import { searchSecurities } from '../api/securityApi.js'
import { addToWatchlist, getWatchlist } from '../api/watchlistApi.js'

vi.mock('../api/securityApi.js', () => ({ searchSecurities: vi.fn() }))
vi.mock('../api/watchlistApi.js', () => ({ addToWatchlist: vi.fn(), getWatchlist: vi.fn() }))

describe('SecuritySearch', () => {
  beforeEach(() => {
    searchSecurities.mockReset()
    addToWatchlist.mockReset()
    getWatchlist.mockReset()
    getWatchlist.mockResolvedValue({ items: [] })
  })
  it('debounces lookup and supports keyboard selection', async () => {
    searchSecurities.mockResolvedValue({ items: [
      { isin: 'INE002A01018', symbol: 'RELIANCE', name: 'Reliance Industries Limited' },
      { isin: 'INE036A01016', symbol: 'RELINFRA', name: 'Reliance Infrastructure Limited' },
    ] })
    const navigate = vi.fn()
    render(<SecuritySearch onNavigate={navigate} onUnauthorized={() => {}} />)
    const input = screen.getByRole('combobox')
    await userEvent.type(input, 'rel')
    await waitFor(() => expect(searchSecurities).toHaveBeenCalledOnce(), { timeout: 1000 })
    expect(screen.queryByText('INE002A01018')).toBeNull()
    expect(screen.queryByText('INE036A01016')).toBeNull()
    await userEvent.keyboard('{ArrowDown}{Enter}')
    expect(navigate).toHaveBeenCalledWith('/securities/RELINFRA')
  })

  it('does not request blank or one-character input', async () => {
    render(<SecuritySearch onNavigate={() => {}} onUnauthorized={() => {}} />)
    await userEvent.type(screen.getByRole('combobox'), 'r')
    await new Promise((resolve) => setTimeout(resolve, 300))
    expect(searchSecurities).not.toHaveBeenCalled()
  })

  it('aborts a superseded lookup', async () => {
    searchSecurities.mockImplementation((query, { signal }) => new Promise((resolve, reject) => {
      signal.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')), { once: true })
    }))
    render(<SecuritySearch onNavigate={() => {}} onUnauthorized={() => {}} />)
    const input = screen.getByRole('combobox')
    await userEvent.type(input, 'rel')
    await waitFor(() => expect(searchSecurities).toHaveBeenCalledOnce(), { timeout: 1000 })
    const firstSignal = searchSecurities.mock.calls[0][1].signal
    await userEvent.type(input, 'i')
    await waitFor(() => expect(firstSignal.aborted).toBe(true))
  })

  it('adds a search result to the user watchlist without navigating', async () => {
    searchSecurities.mockResolvedValue({ items: [
      { isin: 'INE002A01018', symbol: 'RELIANCE', name: 'Reliance Industries Limited' },
    ] })
    addToWatchlist.mockResolvedValue({ isin: 'INE002A01018', added: true })
    const navigate = vi.fn()
    const watchlistChanged = vi.fn()
    render(<SecuritySearch onNavigate={navigate} onUnauthorized={() => {}} onWatchlistChanged={watchlistChanged} />)
    await userEvent.type(screen.getByRole('combobox'), 'rel')
    const addButton = await screen.findByRole('button', { name: 'Add to watchlist: RELIANCE' }, { timeout: 1000 })
    await userEvent.click(addButton)
    expect(addToWatchlist).toHaveBeenCalledWith('INE002A01018', expect.any(Object))
    expect(navigate).not.toHaveBeenCalled()
    expect(watchlistChanged).toHaveBeenCalledWith({ action: 'added', isin: 'INE002A01018' })
    expect((await screen.findByRole('button', { name: 'In watchlist: RELIANCE' })).disabled).toBe(true)
  })
})

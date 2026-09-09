import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import SecuritySearch from './SecuritySearch.jsx'
import { searchSecurities } from '../api/securityApi.js'

vi.mock('../api/securityApi.js', () => ({ searchSecurities: vi.fn() }))

describe('SecuritySearch', () => {
  beforeEach(() => { searchSecurities.mockReset() })
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
    await userEvent.keyboard('{ArrowDown}{Enter}')
    expect(navigate).toHaveBeenCalledWith('/securities/INE036A01016')
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
})

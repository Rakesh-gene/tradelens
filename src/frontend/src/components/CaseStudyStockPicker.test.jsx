import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import CaseStudyStockPicker from './CaseStudyStockPicker.jsx'
import { searchSecurities } from '../api/securityApi.js'

vi.mock('../api/securityApi.js', () => ({ searchSecurities: vi.fn() }))

describe('CaseStudyStockPicker', () => {
  beforeEach(() => searchSecurities.mockReset())

  it('searches stocks and returns the selected security', async () => {
    searchSecurities.mockResolvedValue({ items: [{ isin: 'INE002A01018', symbol: 'RELIANCE', name: 'Reliance Industries Limited' }] })
    const select = vi.fn()
    render(<CaseStudyStockPicker value={null} onChange={select} onUnauthorized={() => {}} />)
    await userEvent.type(screen.getByRole('combobox', { name: 'Stock' }), 'rel')
    await waitFor(() => expect(searchSecurities).toHaveBeenCalledWith({ q: 'rel', limit: 12 }, expect.any(Object)), { timeout: 1000 })
    await userEvent.click(await screen.findByRole('option', { name: /RELIANCE/ }))
    expect(select).toHaveBeenCalledWith(expect.objectContaining({ isin: 'INE002A01018' }))
  })
})

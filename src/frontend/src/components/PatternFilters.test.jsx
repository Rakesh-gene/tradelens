import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import PatternFilters from './PatternFilters.jsx'
import { EMPTY_SETUP_FILTERS } from '../utils/setupFilters.js'

describe('PatternFilters', () => {
  it('applies and clears explicit filter state', async () => {
    const apply = vi.fn((event) => event.preventDefault())
    const clear = vi.fn()
    render(<PatternFilters filters={EMPTY_SETUP_FILTERS} onChange={() => {}} onApply={apply} onClear={clear} />)
    await userEvent.click(screen.getByRole('button', { name: 'Apply filters' }))
    await userEvent.click(screen.getByRole('button', { name: 'Clear' }))
    expect(apply).toHaveBeenCalledOnce()
    expect(clear).toHaveBeenCalledOnce()
    expect(screen.getByRole('option', { name: 'BASE-VCP' })).toBeTruthy()
    expect(screen.getByRole('option', { name: 'BRK-MULTIY' })).toBeTruthy()
    expect(screen.getByRole('option', { name: 'COMP-IB' })).toBeTruthy()
    expect(screen.queryByLabelText('Sector')).toBeNull()
    expect(screen.queryByLabelText('Variant')).toBeNull()
    expect(screen.queryByLabelText('Minimum RS 6M')).toBeNull()
    expect(screen.queryByLabelText('Minimum liquidity')).toBeNull()
  })

  it('closes the mobile drawer with Escape', async () => {
    const close = vi.fn()
    render(<PatternFilters drawer open filters={EMPTY_SETUP_FILTERS} onChange={() => {}} onApply={() => {}} onClear={() => {}} onClose={close} />)
    expect(screen.getByRole('dialog', { name: 'Setup filters' })).toBeTruthy()
    await userEvent.keyboard('{Escape}')
    expect(close).toHaveBeenCalledOnce()
  })
})

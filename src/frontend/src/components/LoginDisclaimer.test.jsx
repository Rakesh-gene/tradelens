import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import LoginDisclaimer, { AUTO_HIDE_MS } from './LoginDisclaimer.jsx'

afterEach(() => vi.useRealTimers())

describe('LoginDisclaimer', () => {
  it('dismisses automatically after ten seconds', () => {
    vi.useFakeTimers()
    const onDismiss = vi.fn()
    render(<LoginDisclaimer onDismiss={onDismiss} />)

    act(() => vi.advanceTimersByTime(AUTO_HIDE_MS - 1))
    expect(onDismiss).not.toHaveBeenCalled()
    act(() => vi.advanceTimersByTime(1))
    expect(onDismiss).toHaveBeenCalledOnce()
  })

  it('can be dismissed immediately', async () => {
    const onDismiss = vi.fn()
    render(<LoginDisclaimer onDismiss={onDismiss} />)

    await userEvent.click(screen.getByRole('button', { name: 'Dismiss risk notice' }))
    expect(onDismiss).toHaveBeenCalledOnce()
  })
})

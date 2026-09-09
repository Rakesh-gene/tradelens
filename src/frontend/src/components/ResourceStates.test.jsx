import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { ResourceState } from './ResourceStates.jsx'

describe('ResourceState', () => {
  it('renders an accessible loading state', () => {
    render(<ResourceState status="loading" />)
    expect(screen.getByLabelText('Loading market evidence…').getAttribute('aria-busy')).toBe('true')
  })

  it('keeps retry available for recoverable failures', async () => {
    const retry = vi.fn()
    render(<ResourceState status="error" error={new Error('Offline')} onRetry={retry} />)
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(retry).toHaveBeenCalledOnce()
  })

  it('does not offer retry for a forbidden response', () => {
    render(<ResourceState status="error" error={{ status: 403, message: 'Admin only' }} onRetry={() => {}} />)
    expect(screen.getByRole('heading', { name: 'Access restricted' })).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Try again' })).toBeNull()
  })
})

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App.jsx'
import { getCurrentUser } from './api/authApi.js'

vi.mock('./api/authApi.js', async (load) => {
  const actual = await load()
  return { ...actual, getCurrentUser: vi.fn() }
})
vi.mock('./pages/OverviewPage.jsx', () => ({ default: () => <h1>Overview fixture</h1> }))
vi.mock('./pages/SetupsPage.jsx', () => ({ default: () => <h1>Setups fixture</h1> }))
vi.mock('./pages/PatternDetailPage.jsx', () => ({ default: () => <h1>Pattern fixture</h1> }))
vi.mock('./pages/SecurityPage.jsx', () => ({ default: () => <h1>Security fixture</h1> }))
vi.mock('./pages/AdminPipelinePage.jsx', () => ({ default: () => <h1>Pipeline fixture</h1> }))

describe('App session routing', () => {
  beforeEach(() => {
    sessionStorage.clear()
    getCurrentUser.mockReset()
    window.history.replaceState({}, '', '/')
  })

  it('validates a token before rendering protected content and signs out with replacement', async () => {
    sessionStorage.setItem('tradelensAccessToken', 'test-token')
    window.history.replaceState({}, '', '/overview')
    getCurrentUser.mockResolvedValue({ user: { email: 'person@example.com', isAdmin: false } })
    render(<App />)
    expect(screen.getByText('Validating your session…')).toBeTruthy()
    expect(await screen.findByRole('heading', { name: 'Overview fixture' })).toBeTruthy()
    await userEvent.click(screen.getByRole('button', { name: 'Sign out' }))
    await waitFor(() => expect(window.location.pathname).toBe('/'))
    expect(sessionStorage.getItem('tradelensAccessToken')).toBeNull()
    expect(screen.queryByText('Overview fixture')).toBeNull()
  })

  it('renders malformed protected identifiers locally without loading a detail page', async () => {
    sessionStorage.setItem('tradelensAccessToken', 'test-token')
    window.history.replaceState({}, '', '/patterns/not-a-uuid')
    getCurrentUser.mockResolvedValue({ user: { email: 'person@example.com' } })
    render(<App />)
    expect(await screen.findByRole('heading', { name: 'This route does not exist.' })).toBeTruthy()
    expect(screen.queryByText('Pattern fixture')).toBeNull()
  })
})

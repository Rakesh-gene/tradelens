import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App.jsx'
import { getCurrentUser, login } from './api/authApi.js'

vi.mock('./api/authApi.js', async (load) => {
  const actual = await load()
  return { ...actual, getCurrentUser: vi.fn(), login: vi.fn() }
})
vi.mock('./pages/OverviewPage.jsx', () => ({ default: () => <h1>Overview fixture</h1> }))
vi.mock('./pages/SectorRotationPage.jsx', () => ({ default: () => <h1>Sector rotation fixture</h1> }))
vi.mock('./pages/SetupsPage.jsx', () => ({ default: () => <h1>Setups fixture</h1> }))
vi.mock('./pages/WatchlistPage.jsx', () => ({ default: () => <h1>Watchlist fixture</h1> }))
vi.mock('./pages/IndicesPage.jsx', () => ({ default: () => <h1>Indices fixture</h1> }))
vi.mock('./pages/PatternDetailPage.jsx', () => ({ default: () => <h1>Pattern fixture</h1> }))
vi.mock('./pages/SecurityPage.jsx', () => ({ default: () => <h1>Security fixture</h1> }))
vi.mock('./pages/AdminPipelinePage.jsx', () => ({ default: () => <h1>Pipeline fixture</h1> }))
vi.mock('./pages/ProfilePage.jsx', () => ({ default: () => <h1>Profile fixture</h1> }))

describe('App session routing', () => {
  beforeEach(() => {
    sessionStorage.clear()
    localStorage.clear()
    getCurrentUser.mockReset()
    login.mockReset()
    window.history.replaceState({}, '', '/')
  })

  it('opens the authenticated profile route and applies the saved user theme', async () => {
    sessionStorage.setItem('tradelensAccessToken', 'test-token')
    window.history.replaceState({}, '', '/profile')
    getCurrentUser.mockResolvedValue({ user: { email: 'person@example.com', theme: 'forest' } })
    render(<App />)
    expect(await screen.findByRole('heading', { name: 'Profile fixture' })).toBeTruthy()
    await waitFor(() => expect(document.documentElement.dataset.theme).toBe('forest'))
    expect(localStorage.getItem('tradelensTheme')).toBe('forest')
  })

  it('shows the header risk notice after a successful login', async () => {
    login.mockResolvedValue({
      accessToken: 'signed-in-token',
      user: { email: 'person@example.com', isAdmin: false },
    })
    getCurrentUser.mockResolvedValue({ user: { email: 'person@example.com', isAdmin: false } })
    render(<App />)

    await userEvent.type(screen.getByLabelText('Email address'), 'person@example.com')
    await userEvent.type(screen.getByLabelText('Password'), 'secret')
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(await screen.findByRole('heading', { name: 'Overview fixture' })).toBeTruthy()
    expect(screen.getByRole('status').textContent).toMatch(/Trading can result in loss of capital/i)
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

  it('opens sector rotation as its own protected page', async () => {
    sessionStorage.setItem('tradelensAccessToken', 'test-token')
    window.history.replaceState({}, '', '/sector-rotation')
    getCurrentUser.mockResolvedValue({ user: { email: 'person@example.com', isAdmin: false } })
    render(<App />)
    expect(await screen.findByRole('heading', { name: 'Sector rotation fixture' })).toBeTruthy()
    expect(screen.queryByText('Overview fixture')).toBeNull()
  })

  it('opens the user watchlist as a protected page', async () => {
    sessionStorage.setItem('tradelensAccessToken', 'test-token')
    window.history.replaceState({}, '', '/watchlist')
    getCurrentUser.mockResolvedValue({ user: { email: 'person@example.com', isAdmin: false } })
    render(<App />)
    expect(await screen.findByRole('heading', { name: 'Watchlist fixture' })).toBeTruthy()
  })

  it('opens the index analysis as a protected future-entitlement page', async () => {
    sessionStorage.setItem('tradelensAccessToken', 'test-token')
    window.history.replaceState({}, '', '/indices')
    getCurrentUser.mockResolvedValue({ user: { email: 'person@example.com', isAdmin: false } })
    render(<App />)
    expect(await screen.findByRole('heading', { name: 'Indices fixture' })).toBeTruthy()
  })

  it('renders malformed protected identifiers locally without loading a detail page', async () => {
    sessionStorage.setItem('tradelensAccessToken', 'test-token')
    window.history.replaceState({}, '', '/patterns/not-a-uuid')
    getCurrentUser.mockResolvedValue({ user: { email: 'person@example.com' } })
    render(<App />)
    expect(await screen.findByRole('heading', { name: 'Page not found' })).toBeTruthy()
    expect(screen.queryByText('Pattern fixture')).toBeNull()
  })
})

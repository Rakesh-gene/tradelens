import React, { useEffect, useState } from 'react'
import LoginPage from './pages/LoginPage.jsx'
import SignupPage from './pages/SignupPage.jsx'
import OverviewPage from './pages/OverviewPage.jsx'
import SetupsPage from './pages/SetupsPage.jsx'
import PatternDetailPage from './pages/PatternDetailPage.jsx'
import SecurityPage from './pages/SecurityPage.jsx'
import AdminPipelinePage from './pages/AdminPipelinePage.jsx'
import AppShell from './components/AppShell.jsx'
import { TOKEN_KEY } from './apiClient.js'

function locationPath() { return window.location.pathname.replace(/\/+$/, '') || '/' }
function protectedPath(path) { return path === '/overview' || path === '/setups' || path === '/admin/pipeline' || path.startsWith('/patterns/') || path.startsWith('/securities/') }

export default function App() {
  const [pathname, setPathname] = useState(locationPath)
  const [user, setUser] = useState(null)
  const [checkingSession, setCheckingSession] = useState(true)
  const navigate = (next, replace = false) => { window.history[replace ? 'replaceState' : 'pushState']({}, '', next); setPathname(next.split('?')[0].replace(/\/+$/, '') || '/') }

  useEffect(() => { const pop = () => setPathname(locationPath()); window.addEventListener('popstate', pop); return () => window.removeEventListener('popstate', pop) }, [])
  useEffect(() => {
    if (!protectedPath(pathname)) { setCheckingSession(false); return }
    if (!window.sessionStorage.getItem(TOKEN_KEY)) { setUser(null); navigate('/', true); setCheckingSession(false); return }
    setCheckingSession(true)
    const controller = new AbortController()
    const validateSession = (initial = false) => {
      const token = window.sessionStorage.getItem(TOKEN_KEY)
      if (!token) return Promise.resolve()
      return fetch('/api/auth/me', { signal: controller.signal, headers: { Authorization: `Bearer ${token}` } })
        .then(async (response) => {
          if (response.status === 401) {
            const error = new Error('Session expired')
            error.unauthorized = true
            throw error
          }
          if (!response.ok) throw new Error(`Session validation failed (${response.status})`)
          return response.json()
        })
        .then((payload) => {
          if (payload.accessToken) window.sessionStorage.setItem(TOKEN_KEY, payload.accessToken)
          setUser(payload.user)
          if (pathname === '/admin/pipeline' && !payload.user?.isAdmin) navigate('/overview', true)
        })
        .catch((error) => {
          if (error.name !== 'AbortError' && error.unauthorized) {
            window.sessionStorage.removeItem(TOKEN_KEY); setUser(null); navigate('/', true)
          }
        })
        .finally(() => { if (initial) setCheckingSession(false) })
    }
    validateSession(true)
    const timer = window.setInterval(validateSession, 5 * 60 * 1000)
    const onVisibilityChange = () => { if (document.visibilityState === 'visible') validateSession() }
    document.addEventListener('visibilitychange', onVisibilityChange)
    return () => {
      controller.abort()
      window.clearInterval(timer)
      document.removeEventListener('visibilitychange', onVisibilityChange)
    }
  }, [pathname])

  const authenticated = (token, nextUser) => { window.sessionStorage.setItem(TOKEN_KEY, token); setUser(nextUser); navigate('/overview') }
  const signOut = () => { window.sessionStorage.removeItem(TOKEN_KEY); setUser(null); navigate('/', true) }
  if (pathname === '/signup') return <SignupPage />
  if (!protectedPath(pathname)) return <LoginPage onAuthenticated={authenticated} />
  if (checkingSession) return <main className="session-loading">Validating your session…</main>
  const common = { onNavigate: navigate, onUnauthorized: signOut }
  let page = <OverviewPage {...common} />
  if (pathname === '/setups') page = <SetupsPage {...common} />
  else if (pathname.startsWith('/patterns/')) page = <PatternDetailPage patternId={decodeURIComponent(pathname.slice(10))} {...common} />
  else if (pathname.startsWith('/securities/')) page = <SecurityPage isin={decodeURIComponent(pathname.slice(12))} {...common} />
  else if (pathname === '/admin/pipeline' && (user?.isAdmin || user?.is_admin)) page = <AdminPipelinePage {...common} />
  return <AppShell user={user} onNavigate={navigate} onSignOut={signOut}>{page}</AppShell>
}

import React, { lazy, Suspense, useCallback, useEffect, useState } from 'react'
import LoginPage from './pages/LoginPage.jsx'
import SignupPage from './pages/SignupPage.jsx'
import NotFoundPage from './pages/NotFoundPage.jsx'
import AppShell from './components/AppShell.jsx'
import { getCurrentUser } from './api/authApi.js'
import { clearAccessToken, readAccessToken, writeAccessToken } from './auth/authSession.js'
import { isProtectedRoute, matchRoute } from './routing/routes.js'
import { rememberCurrentSetupsLocation, rememberedSetupsLocation } from './setupNavigation.js'
import { applyTheme, readTheme } from './themePreferences.js'
import ProductGuideTour from './components/ProductGuideTour.jsx'

const OverviewPage = lazy(() => import('./pages/OverviewPage.jsx'))
const SectorRotationPage = lazy(() => import('./pages/SectorRotationPage.jsx'))
const SetupsPage = lazy(() => import('./pages/SetupsPage.jsx'))
const WatchlistPage = lazy(() => import('./pages/WatchlistPage.jsx'))
const IndicesPage = lazy(() => import('./pages/IndicesPage.jsx'))
const PatternDetailPage = lazy(() => import('./pages/PatternDetailPage.jsx'))
const SecurityPage = lazy(() => import('./pages/SecurityPage.jsx'))
const AdminPipelinePage = lazy(() => import('./pages/AdminPipelinePage.jsx'))
const ProfilePage = lazy(() => import('./pages/ProfilePage.jsx'))
const CaseStudiesPage = lazy(() => import('./pages/CaseStudiesPage.jsx'))
const CaseStudyDetailPage = lazy(() => import('./pages/CaseStudyDetailPage.jsx'))
const AdminCaseStudyPage = lazy(() => import('./pages/AdminCaseStudyPage.jsx'))
const GuidePage = lazy(() => import('./pages/GuidePage.jsx'))

function currentLocation() {
  return `${window.location.pathname}${window.location.search}`
}

export default function App() {
  const [location, setLocation] = useState(currentLocation)
  const [user, setUser] = useState(null)
  const [checkingSession, setCheckingSession] = useState(true)
  const [sessionError, setSessionError] = useState('')
  const [sessionRevision, setSessionRevision] = useState(0)
  const [authNotice, setAuthNotice] = useState('')
  const [showLoginDisclaimer, setShowLoginDisclaimer] = useState(false)
  const [theme, setTheme] = useState(readTheme)
  const [watchlistRevision, setWatchlistRevision] = useState(0)
  const [guideTour, setGuideTour] = useState({ active: false, stepIndex: 0 })
  const route = matchRoute(window.location.pathname)
  const dismissLoginDisclaimer = useCallback(() => setShowLoginDisclaimer(false), [])

  useEffect(() => { applyTheme(theme) }, [theme])

  const navigate = (next, { replace = false } = {}) => {
    rememberCurrentSetupsLocation()
    const destination = next === '/setups' ? rememberedSetupsLocation() : next
    window.history[replace ? 'replaceState' : 'pushState']({}, '', destination)
    setLocation(currentLocation())
  }

  useEffect(() => {
    const handlePopState = () => setLocation(currentLocation())
    window.addEventListener('popstate', handlePopState)
    return () => window.removeEventListener('popstate', handlePopState)
  }, [])

  useEffect(() => {
    if (!isProtectedRoute(route)) {
      setCheckingSession(false)
      setSessionError('')
      return undefined
    }
    if (!readAccessToken()) {
      setUser(null)
      navigate('/', { replace: true })
      setCheckingSession(false)
      return undefined
    }

    setCheckingSession(true)
    setSessionError('')
    const controller = new AbortController()
    const validateSession = (initial = false) => {
      const token = readAccessToken()
      if (!token) return Promise.resolve()
      return getCurrentUser(token, { signal: controller.signal })
        .then((payload) => {
          if (payload.accessToken) writeAccessToken(payload.accessToken)
          setUser(payload.user)
          if (payload.user?.theme) setTheme(payload.user.theme)
          setSessionError('')
          if (route.admin && !payload.user?.isAdmin && !payload.user?.is_admin) {
            navigate('/overview', { replace: true })
          }
        })
        .catch((error) => {
          if (error.name === 'AbortError') return
          if (error.status === 401) {
            clearAccessToken()
            setUser(null)
            setAuthNotice('Your session expired. Please sign in again.')
            navigate('/', { replace: true })
          } else {
            setSessionError(error.message || 'TradeLens could not validate your session.')
          }
        })
        .finally(() => { if (initial) setCheckingSession(false) })
    }

    validateSession(true)
    const timer = window.setInterval(validateSession, 5 * 60 * 1000)
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') validateSession()
    }
    document.addEventListener('visibilitychange', handleVisibilityChange)
    return () => {
      controller.abort()
      window.clearInterval(timer)
      document.removeEventListener('visibilitychange', handleVisibilityChange)
    }
  }, [location, sessionRevision])

  const authenticated = (token, nextUser) => {
    writeAccessToken(token)
    setUser(nextUser)
    if (nextUser?.theme) setTheme(nextUser.theme)
    setAuthNotice('')
    setShowLoginDisclaimer(true)
    navigate('/overview', { replace: true })
  }
  const registered = () => {
    setAuthNotice('Account created. Sign in with your new credentials.')
    navigate('/', { replace: true })
  }
  const signOut = () => {
    clearAccessToken()
    setUser(null)
    setShowLoginDisclaimer(false)
    setAuthNotice('You have signed out.')
    navigate('/', { replace: true })
  }
  const startGuideTour = () => { setGuideTour({ active: true, stepIndex: 0 }); navigate('/overview') }

  if (route.name === 'signup') return <SignupPage onRegistered={registered} />
  if (route.name === 'login') return <LoginPage notice={authNotice} onAuthenticated={authenticated} />
  if (!isProtectedRoute(route)) return <NotFoundPage onNavigate={navigate} withFooter />
  if (checkingSession) return <main className="session-loading">Validating your session…</main>
  if (sessionError) {
    return <main className="standalone-state">
      <p className="eyebrow">Session check unavailable</p>
      <h1>We could not verify your session.</h1>
      <p>{sessionError}</p>
      <button className="primary-button" type="button" onClick={() => { setCheckingSession(true); setSessionRevision((value) => value + 1) }}>Try again</button>
    </main>
  }

  const common = { onNavigate: navigate, onUnauthorized: signOut, isAdmin: Boolean(user?.isAdmin || user?.is_admin) }
  let page = <NotFoundPage onNavigate={navigate} />
  if (route.name === 'overview') page = <OverviewPage {...common} />
  else if (route.name === 'sector-rotation') page = <SectorRotationPage key={location} {...common} />
  else if (route.name === 'setups') page = <SetupsPage key={location} {...common} />
  else if (route.name === 'watchlist') page = <WatchlistPage {...common} revision={watchlistRevision} />
  else if (route.name === 'indices') page = <IndicesPage key={location} {...common} />
  else if (route.name === 'guide') page = <GuidePage {...common} onStartTour={startGuideTour} />
  else if (route.name === 'pattern-detail') page = <PatternDetailPage patternId={route.params.patternId} {...common} />
  else if (route.name === 'security') page = <SecurityPage symbol={route.params.symbol} {...common} />
  else if (route.name === 'index-detail') page = <SecurityPage indexCode={route.params.code} {...common} />
  else if (route.name === 'profile') page = <ProfilePage {...common} user={user} theme={theme} onThemeChange={setTheme} onProfileUpdated={setUser} />
  else if (route.name === 'case-studies') page = <CaseStudiesPage key={location} {...common} />
  else if (route.name === 'case-study-detail') page = <CaseStudyDetailPage caseStudyId={route.params.caseStudyId} {...common} />
  else if (route.name === 'admin-pipeline' && (user?.isAdmin || user?.is_admin)) page = <AdminPipelinePage {...common} />
  else if (route.name === 'admin-case-studies' && (user?.isAdmin || user?.is_admin)) page = <AdminCaseStudyPage {...common} />

  page = <>{page}<ProductGuideTour active={guideTour.active} stepIndex={guideTour.stepIndex} pathname={window.location.pathname} onStepIndexChange={(stepIndex) => setGuideTour((current) => ({ ...current, stepIndex }))} onFinish={() => setGuideTour({ active: false, stepIndex: 0 })} /></>

  return <AppShell user={user} onNavigate={navigate} onSignOut={signOut} onWatchlistChanged={() => setWatchlistRevision((value) => value + 1)} showLoginDisclaimer={showLoginDisclaimer} onDismissLoginDisclaimer={dismissLoginDisclaimer}><Suspense fallback={<section className="loading-panel" aria-busy="true"><p>Loading page…</p></section>}>{page}</Suspense></AppShell>
}

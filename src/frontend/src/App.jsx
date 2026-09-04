import LoginPage from './pages/LoginPage.jsx'
import SignupPage from './pages/SignupPage.jsx'
import React from 'react'
import { useEffect, useState } from 'react'
import OverviewPage from './pages/OverviewPage.jsx'

function getPathname() {
  return window.location.pathname.replace(/\/+$/, '') || '/'
}

export default function App() {
  const [pathname, setPathname] = useState(getPathname)
  const [user, setUser] = useState(null)
  const [checkingSession, setCheckingSession] = useState(true)

  const navigate = (nextPathname, replace = false) => {
    window.history[replace ? 'replaceState' : 'pushState']({}, '', nextPathname)
    setPathname(nextPathname)
  }

  useEffect(() => {
    const handlePopState = () => setPathname(getPathname())
    window.addEventListener('popstate', handlePopState)
    return () => window.removeEventListener('popstate', handlePopState)
  }, [])

  useEffect(() => {
    if (pathname !== '/overview') {
      setCheckingSession(false)
      return
    }
    const token = window.sessionStorage.getItem('tradelensAccessToken')
    if (!token) {
      setUser(null)
      navigate('/', true)
      setCheckingSession(false)
      return
    }
    setCheckingSession(true)
    fetch('/api/auth/me', { headers: { Authorization: `Bearer ${token}` } })
      .then(async (response) => {
        if (!response.ok) throw new Error('Session expired')
        return response.json()
      })
      .then((payload) => setUser(payload.user))
      .catch(() => {
        window.sessionStorage.removeItem('tradelensAccessToken')
        setUser(null)
        navigate('/', true)
      })
      .finally(() => setCheckingSession(false))
  }, [pathname])

  const handleAuthenticated = (accessToken, authenticatedUser) => {
    window.sessionStorage.setItem('tradelensAccessToken', accessToken)
    setUser(authenticatedUser)
    navigate('/overview')
  }

  const handleSignOut = () => {
    window.sessionStorage.removeItem('tradelensAccessToken')
    setUser(null)
    navigate('/', true)
  }

  if (pathname === '/signup') {
    return <SignupPage />
  }

  if (pathname === '/overview') {
    return checkingSession ? <main className="session-loading">Loading your overview…</main> : <OverviewPage user={user} onSignOut={handleSignOut} />
  }

  return <LoginPage onAuthenticated={handleAuthenticated} />
}

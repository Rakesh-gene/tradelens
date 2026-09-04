import LoginPage from './pages/LoginPage.jsx'
import SignupPage from './pages/SignupPage.jsx'

function getPathname() {
  return window.location.pathname.replace(/\/+$/, '') || '/'
}

export default function App() {
  const pathname = getPathname()

  if (pathname === '/signup') {
    return <SignupPage />
  }

  return <LoginPage />
}

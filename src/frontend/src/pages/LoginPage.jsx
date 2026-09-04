import AuthForm from '../components/AuthForm.jsx'

import React from 'react'

const navItems = ['Screens', 'Breakouts', 'Market', 'Learn']

const loginFields = [
  {
    name: 'email',
    label: 'Email address',
    type: 'email',
    placeholder: 'name@company.com',
    autoComplete: 'email',
  },
  {
    name: 'password',
    label: 'Password',
    type: 'password',
    placeholder: 'Enter your password',
    autoComplete: 'current-password',
  },
]

export default function LoginPage({ onAuthenticated }) {
  return (
    <main className="login-shell">
      <section className="left-panel" aria-hidden="true">
        <header className="topbar">
          <div className="brand-lockup">
            <div className="brand-mark">TL</div>
            <div>
              <p className="brand-name">Tradelens</p>
              <p className="brand-meta">Watch the market show its hand.</p>
            </div>
          </div>

          <nav className="topnav" aria-label="Primary">
            {navItems.map((item) => (
              <span key={item}>{item}</span>
            ))}
          </nav>
        </header>

        <div className="hero-copy">
          <p className="eyebrow">Secure access</p>
          <h1>Sign in to the screen that measures the close.</h1>
          <p className="hero-description">
            A focused login for charts, scans, and the breakout record. Built
            to feel like Tradelens, with the same calm, rules-first tone.
          </p>
        </div>

      </section>

      <section className="right-panel" aria-label="Login form">
        <AuthForm
          title="Welcome back."
          description={{
            subtitle: 'Sign in to continue',
            dividerLabel: 'or use your password',
            switchText: 'Need an account?',
            successMessage: 'Signed in successfully.',
          }}
          actionLabel="Email sign-in link"
          altActionLabel="Create an account"
          altActionHref="/signup"
          fields={loginFields}
          submitLabel="Sign in"
          footer={
            <div className="form-row">
              <label className="checkbox">
                <input type="checkbox" defaultChecked />
                <span>Remember me</span>
              </label>

              <a href="/" className="link">
                Forgot password?
              </a>
            </div>
          }
          onSubmit={async (values) => {
            const response = await fetch('/api/login', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(values),
            })
            const payload = await response.json()
            if (!response.ok) {
              throw new Error(payload.error || 'Unable to sign in')
            }
            onAuthenticated(payload.accessToken, payload.user)
          }}
        />

        <p className="legal-copy">
          Not financial advice. Tradelens is a stock screening and market
          analytics tool, not a recommendation engine.
        </p>
      </section>
    </main>
  )
}

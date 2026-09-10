import AuthForm from '../components/AuthForm.jsx'
import SiteFooter from '../components/SiteFooter.jsx'
import { login } from '../api/authApi.js'

import React from 'react'

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

export default function LoginPage({ notice, onAuthenticated }) {
  return (
    <div className="public-shell">
    <main className="login-shell">
      <section className="left-panel" aria-hidden="true">
        <header className="topbar">
          <div className="brand-lockup">
            <div className="brand-mark">TL</div>
            <div>
              <p className="brand-name">Tradelens</p>
            </div>
          </div>
        </header>

        <div className="hero-copy">
          <h1>End-of-day market analysis.</h1>
          <p className="hero-description">Review setups, evidence, and risk levels.</p>
        </div>

      </section>

      <section className="right-panel" aria-label="Login form">
        {notice && <p className="form-message success" role="status">{notice}</p>}
        <AuthForm
          title="Welcome back."
          description={{
            subtitle: 'Sign in to continue',
            switchText: 'Need an account?',
            successMessage: 'Signed in successfully.',
          }}
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
            const payload = await login(values)
            if (!payload.accessToken || !payload.user) {
              throw new Error('The sign-in service returned an incomplete response. Please try again.')
            }
            onAuthenticated(payload.accessToken, payload.user)
          }}
        />
      </section>
    </main>
    <SiteFooter />
    </div>
  )
}

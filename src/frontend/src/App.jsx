import { useState } from 'react'

const trustMarks = [
  'Biometric verification',
  'Two-factor protected',
  'Enterprise-grade encryption',
]

const fieldCopy = {
  email: 'Work email',
  password: 'Password',
}

export default function App() {
  const [rememberMe, setRememberMe] = useState(true)
  const [showPassword, setShowPassword] = useState(false)

  const accountSummary = [
    { label: 'Protected sessions', value: '24/7' },
    { label: 'Average login time', value: '12 sec' },
    { label: 'Global teams', value: '18k+' },
  ]

  return (
    <main className="login-shell">
      <section className="login-hero" aria-hidden="true">
        <div className="pattern pattern-one" />
        <div className="pattern pattern-two" />
        <div className="hero-copy">
          <span className="eyebrow">TradeLens Access</span>
          <h1>Log in to your trading workspace.</h1>
          <p>
            Move between markets, research, and portfolio insights from a single
            secure dashboard.
          </p>
        </div>
        <ul className="trust-list">
          {trustMarks.map((mark) => (
            <li key={mark}>{mark}</li>
          ))}
        </ul>
      </section>

      <section className="login-card" aria-label="Login form">
        <div className="brand-row">
          <div className="brand-mark">TL</div>
          <div>
            <p className="brand-name">TradeLens</p>
            <p className="brand-subtitle">Sign in to continue</p>
          </div>
        </div>

        <form className="login-form">
          <label className="field">
            <span>{fieldCopy.email}</span>
            <input type="email" name="email" placeholder="name@company.com" autoComplete="email" />
          </label>

          <label className="field">
            <span>{fieldCopy.password}</span>
            <div className="password-row">
              <input
                type={showPassword ? 'text' : 'password'}
                name="password"
                placeholder="Enter your password"
                autoComplete="current-password"
              />
              <button
                type="button"
                className="ghost-button"
                onClick={() => setShowPassword((value) => !value)}
                aria-pressed={showPassword}
              >
                {showPassword ? 'Hide' : 'Show'}
              </button>
            </div>
          </label>

          <div className="form-row">
            <label className="checkbox">
              <input
                type="checkbox"
                checked={rememberMe}
                onChange={(event) => setRememberMe(event.target.checked)}
              />
              <span>Remember me</span>
            </label>
            <a href="/" className="link">
              Forgot password?
            </a>
          </div>

          <button type="submit" className="primary-button">
            Continue
          </button>
        </form>

        <div className="card-footer">
          {accountSummary.map((item) => (
            <div key={item.label}>
              <strong>{item.value}</strong>
              <span>{item.label}</span>
            </div>
          ))}
        </div>
      </section>
    </main>
  )
}

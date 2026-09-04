import { useState } from 'react'

const navItems = ['Screens', 'Breakouts', 'Market', 'Learn']

const accountBullets = [
  'Free account unlocks the private watchlist',
  'Email link or Google sign-in supported',
  'Published methodology, no hidden screeners',
]

const loginSteps = [
  'Enter your email address',
  'Choose password or sign-in link',
  'Open the live market screen',
]

const stats = [
  { value: '1 in 3', label: 'Winning trades' },
  { value: 'After close', label: 'Fresh scans' },
  { value: 'No tips', label: 'Only rules' },
]

export default function App() {
  const [rememberMe, setRememberMe] = useState(true)
  const [showPassword, setShowPassword] = useState(false)

  return (
    <main className="login-shell">
      <section className="left-panel" aria-hidden="true">
        <header className="topbar">
          <div className="brand-lockup">
            <div className="brand-mark">BP</div>
            <div>
              <p className="brand-name">BananaPatterns</p>
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
            to feel like BananaPatterns, with the same calm, rules-first tone.
          </p>
        </div>

        <div className="search-card">
          <div className="search-row">
            <span className="search-pill">Risk first, always</span>
            <span className="search-input">Search any stock</span>
          </div>
          <p className="search-note">
            Every liquid stock, measured after the close.
          </p>
        </div>

        <div className="bullet-grid">
          {accountBullets.map((item) => (
            <article key={item} className="bullet-card">
              <span className="bullet-dot" />
              <p>{item}</p>
            </article>
          ))}
        </div>

        <footer className="left-footer">
          <div>
            <p className="footer-label">Loading today&apos;s scan…</p>
            <strong>The breakout record, updated after each close</strong>
          </div>
          <ul className="stat-list" aria-label="Product highlights">
            {stats.map((stat) => (
              <li key={stat.label}>
                <strong>{stat.value}</strong>
                <span>{stat.label}</span>
              </li>
            ))}
          </ul>
        </footer>
      </section>

      <section className="right-panel" aria-label="Login form">
        <div className="login-card">
          <div className="login-header">
            <div>
              <p className="panel-kicker">BananaPatterns</p>
              <h2>Welcome back.</h2>
            </div>
            <p className="panel-subtitle">Sign in to continue</p>
          </div>

          <div className="auth-actions">
            <button type="button" className="secondary-button">
              Continue with Google
            </button>
            <button type="button" className="secondary-button secondary-quiet">
              Email sign-in link
            </button>
          </div>

          <div className="divider">
            <span>or use your password</span>
          </div>

          <form className="login-form">
            <label className="field">
              <span>Email address</span>
              <input
                type="email"
                name="email"
                placeholder="name@company.com"
                autoComplete="email"
              />
            </label>

            <label className="field">
              <span>Password</span>
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
              Sign in
            </button>
          </form>

          <div className="step-card">
            {loginSteps.map((step, index) => (
              <div key={step} className="step-row">
                <span>{index + 1}</span>
                <p>{step}</p>
              </div>
            ))}
          </div>

          <p className="legal-copy">
            Not financial advice. BananaPatterns is a stock screening and
            market analytics tool, not a recommendation engine.
          </p>
        </div>
      </section>
    </main>
  )
}

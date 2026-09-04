import React from 'react'

export default function OverviewPage({ user, onSignOut }) {
  return (
    <main className="overview-shell">
      <header className="overview-header">
        <div className="brand-lockup">
          <div className="brand-mark">TL</div>
          <div>
            <p className="brand-name">Tradelens</p>
            <p className="brand-meta">Market overview</p>
          </div>
        </div>
        <button type="button" className="secondary-button" onClick={onSignOut}>
          Sign out
        </button>
      </header>

      <section className="overview-hero">
        <p className="eyebrow">Temporary overview</p>
        <h1>Welcome back, {user?.email}.</h1>
        <p>Your market workspace is ready. Live scans and watchlists will appear here next.</p>
      </section>

      <section className="overview-grid" aria-label="Overview placeholders">
        <article><span>Market status</span><strong>Ready for the close</strong></article>
        <article><span>Watchlist</span><strong>No symbols pinned yet</strong></article>
        <article><span>Latest scan</span><strong>Available after market close</strong></article>
      </section>
    </main>
  )
}

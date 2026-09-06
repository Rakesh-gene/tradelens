import React, { useState } from 'react'

export default function AppShell({ children, user, onNavigate, onSignOut }) {
  const [isin, setIsin] = useState('')
  const openSecurity = (event) => {
    event.preventDefault()
    const value = isin.trim().toUpperCase()
    if (value) onNavigate(`/securities/${encodeURIComponent(value)}`)
  }
  return (
    <div className="product-shell">
      <a className="skip-link" href="#main-content">Skip to content</a>
      <header className="app-header">
        <button className="brand-button" type="button" onClick={() => onNavigate('/overview')} aria-label="TradeLens overview">
          <span className="brand-mark">TL</span><span><strong>Tradelens</strong><small>Position intelligence</small></span>
        </button>
        <nav className="app-nav" aria-label="Primary navigation">
          <button type="button" onClick={() => onNavigate('/overview')}>Overview</button>
          <button type="button" onClick={() => onNavigate('/setups')}>Setups</button>
          {(user?.isAdmin || user?.is_admin) && <button type="button" onClick={() => onNavigate('/admin/pipeline')}>Pipeline</button>}
        </nav>
        <form className="security-jump" onSubmit={openSecurity}>
          <label htmlFor="security-isin">Open security by ISIN</label>
          <div><input id="security-isin" value={isin} onChange={(event) => setIsin(event.target.value)} placeholder="INE…" /><button type="submit">Open</button></div>
        </form>
        <div className="user-menu"><span title={user?.email}>{user?.email}</span><button type="button" className="secondary-button" onClick={onSignOut}>Sign out</button></div>
      </header>
      <main id="main-content" className="product-content">{children}</main>
    </div>
  )
}

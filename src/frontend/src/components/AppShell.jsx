import React from 'react'
import NavigationLink from './NavigationLink.jsx'
import SecuritySearch from './SecuritySearch.jsx'

export default function AppShell({ children, user, onNavigate, onSignOut }) {
  return <div className="product-shell">
    <a className="skip-link" href="#main-content">Skip to content</a>
    <header className="app-header">
      <NavigationLink className="brand-button" to="/overview" onNavigate={onNavigate} aria-label="TradeLens overview"><span className="brand-mark">TL</span><span><strong>Tradelens</strong><small>Position intelligence</small></span></NavigationLink>
      <nav className="app-nav" aria-label="Primary navigation">
        <NavigationLink to="/overview" onNavigate={onNavigate}>Overview</NavigationLink>
        <NavigationLink to="/setups" onNavigate={onNavigate}>Setups</NavigationLink>
        {(user?.isAdmin || user?.is_admin) && <NavigationLink to="/admin/pipeline" onNavigate={onNavigate}>Pipeline</NavigationLink>}
      </nav>
      <SecuritySearch onNavigate={onNavigate} onUnauthorized={onSignOut} />
      <div className="user-menu"><span title={user?.email}>{user?.email}</span><button type="button" className="secondary-button" onClick={onSignOut}>Sign out</button></div>
    </header>
    <main id="main-content" className="product-content">{children}</main>
  </div>
}

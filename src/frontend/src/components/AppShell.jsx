import React from 'react'
import NavigationLink from './NavigationLink.jsx'
import SecuritySearch from './SecuritySearch.jsx'
import SiteFooter from './SiteFooter.jsx'

export default function AppShell({ children, user, onNavigate, onSignOut }) {
  const accountInitial = user?.email?.trim()?.charAt(0).toUpperCase() || 'U'
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
      <div className="user-menu">
        <NavigationLink className="account-button" to="/profile" onNavigate={onNavigate} aria-label={`Open profile for ${user?.email || 'current user'}`}>
          <span className="account-avatar" aria-hidden="true">{accountInitial}</span>
          <span className="account-copy"><strong>{user?.email}</strong><small>Profile settings</small></span>
          <svg className="account-chevron" aria-hidden="true" viewBox="0 0 20 20" fill="none"><path d="m7.5 5 5 5-5 5" /></svg>
        </NavigationLink>
        <button type="button" className="header-action header-action--signout" onClick={onSignOut} aria-label="Sign out">
          <svg aria-hidden="true" viewBox="0 0 24 24" fill="none"><path d="M10 5H6.5A1.5 1.5 0 0 0 5 6.5v11A1.5 1.5 0 0 0 6.5 19H10M14.5 8.5 18 12l-3.5 3.5M9 12h9" /></svg>
          <span>Sign out</span>
        </button>
      </div>
    </header>
    <main id="main-content" className="product-content">{children}</main>
    <SiteFooter />
  </div>
}

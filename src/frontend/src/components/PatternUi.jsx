import React from 'react'
import { formatMarketDate, formatPercent, formatPrice, formatScore, labelize } from '../formatters.js'

export function StateBadge({ state }) {
  const group = ['READY', 'MATURE', 'RUNNING'].includes(state) ? 'actionable' : ['TRIGGERED', 'CONFIRMED', 'COMPLETED'].includes(state) ? 'active' : ['FAILED', 'PARTIAL', 'CANCELLED', 'INVALIDATED', 'EXPIRED'].includes(state) ? 'terminal' : 'developing'
  return <span className={`state-badge state-badge--${group}`}><span aria-hidden="true">◆</span>{state || 'UNKNOWN'}</span>
}

export function Score({ label, value }) {
  const width = Math.max(0, Math.min(100, Number(value) || 0))
  return <div className="score"><div><span>{label}</span><strong>{formatScore(value)}</strong></div><div className="score-track" aria-hidden="true"><span style={{ width: `${width}%` }} /></div></div>
}

export function SetupCard({ setup, onNavigate }) {
  return <article className="setup-card">
    <div className="setup-card__head"><div><p className="eyebrow">{setup.patternClass}</p><h3>{setup.security?.symbol || setup.security?.isin}</h3><p>{setup.security?.name}</p></div><StateBadge state={setup.state} /></div>
    <div className="setup-card__pattern"><strong>{setup.variant || setup.patternType}</strong><span>{setup.patternType}</span></div>
    <div className="setup-card__metrics"><span>Setup <strong>{formatScore(setup.setupScore)}</strong></span><span>Quality <strong>{formatScore(setup.qualityScore)}</strong></span><span>Pivot <strong>{formatPrice(setup.pivotPrice)}</strong></span><span>Distance <strong>{formatPercent(setup.distanceToPivotPct)}</strong></span></div>
    <div className="tag-list">{setup.evidenceCount > 1 && <span>{setup.evidenceCount} signals</span>}{(setup.supportingPatterns || []).slice(0, 3).map((item) => <span key={item}>{item}</span>)}</div>
    <button type="button" className="text-button" onClick={() => onNavigate(`/patterns/${setup.patternInstanceId}`)}>Inspect evidence →</button>
  </article>
}

export function ResourceState({ status, error, onRetry, children }) {
  if (status === 'loading') return <section className="loading-panel" aria-busy="true"><div /><div /><div /><p>Loading market evidence…</p></section>
  if (status === 'error') return <section className="empty-panel" role="alert"><h2>Data unavailable</h2><p>{error.message}</p><button className="secondary-button" type="button" onClick={onRetry}>Try again</button></section>
  return <>{children}</>
}

export function MeasurementGrid({ values }) {
  const entries = Object.entries(values || {}).filter(([, value]) => value != null && typeof value !== 'object')
  if (!entries.length) return <p className="muted-copy">No measurements available for this section.</p>
  return <dl className="measurement-grid">{entries.map(([key, value]) => <div key={key}><dt>{labelize(key)}</dt><dd>{typeof value === 'boolean' ? (value ? 'Yes' : 'No') : String(value)}</dd></div>)}</dl>
}

export function PageIntro({ eyebrow, title, description, date }) {
  return <header className="page-intro"><div><p className="eyebrow">{eyebrow}</p><h1>{title}</h1><p>{description}</p></div>{date && <div className="date-chip"><span>Data as of</span><strong>{formatMarketDate(date)}</strong></div>}</header>
}

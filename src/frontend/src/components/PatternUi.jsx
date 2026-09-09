import React from 'react'
import { formatMarketDate, formatPercent, formatPrice, formatScore, labelize } from '../utils/formatters.js'
import NavigationLink from './NavigationLink.jsx'
import { buildPatternPath } from '../routing/routes.js'
import LifecycleBadge from './LifecycleBadge.jsx'
import { ScoreGauge } from './ScoreBreakdown.jsx'
import { ResourceState as SharedResourceState } from './ResourceStates.jsx'

export function StateBadge({ state }) {
  return <LifecycleBadge state={state} />
}

export function Score({ label, value }) {
  return <ScoreGauge label={label} value={value} />
}

export function SetupCard({ setup, onNavigate }) {
  return <article className="setup-card">
    <div className="setup-card__head"><div><p className="eyebrow">{setup.patternClass}</p><h3>{setup.security?.symbol || setup.security?.isin}</h3><p>{setup.security?.name}</p></div><StateBadge state={setup.state} /></div>
    <div className="setup-card__pattern"><strong>{setup.variant || setup.patternType}</strong><span>{setup.patternType}</span></div>
    <div className="setup-card__metrics"><span>Best fit <strong>{formatScore(setup.bestFit?.score)}</strong><small>{setup.bestFit?.tier || 'UNRANKED'} · #{setup.bestFit?.rankWithinState || '—'} in {setup.state}</small></span><span>Setup <strong>{formatScore(setup.setupScore)}</strong></span><span>Quality <strong>{formatScore(setup.qualityScore)}</strong></span><span>Pivot <strong>{formatPrice(setup.pivotPrice)}</strong></span><span>Distance <strong>{formatPercent(setup.distanceToPivotPct)}</strong></span></div>
    {setup.bestFit && <div className="best-fit-summary"><p>{setup.bestFit.strengths?.[0] || 'No leading strength identified yet.'}</p>{setup.bestFit.cautions?.[0] && <p className="muted-copy">Watch: {setup.bestFit.cautions[0]}</p>}</div>}
    <div className="tag-list">{setup.evidenceCount > 1 && <span>{setup.evidenceCount} signals</span>}{(setup.supportingPatterns || []).slice(0, 3).map((item) => <span key={item}>{item}</span>)}</div>
    <NavigationLink className="text-button" to={buildPatternPath(setup.patternInstanceId)} onNavigate={onNavigate}>Inspect evidence →</NavigationLink>
  </article>
}

export function ResourceState({ status, error, onRetry, children }) {
  return <SharedResourceState status={status} error={error} onRetry={onRetry}>{children}</SharedResourceState>
}

export function MeasurementGrid({ values }) {
  const entries = Object.entries(values || {}).filter(([, value]) => value != null && typeof value !== 'object')
  if (!entries.length) return <p className="muted-copy">No measurements available for this section.</p>
  return <dl className="measurement-grid">{entries.map(([key, value]) => <div key={key}><dt>{labelize(key)}</dt><dd>{typeof value === 'boolean' ? (value ? 'Yes' : 'No') : String(value)}</dd></div>)}</dl>
}

export function PageIntro({ eyebrow, title, description, date }) {
  return <header className="page-intro"><div><p className="eyebrow">{eyebrow}</p><h1>{title}</h1><p>{description}</p></div>{date && <div className="date-chip"><span>Data as of</span><strong>{formatMarketDate(date)}</strong></div>}</header>
}

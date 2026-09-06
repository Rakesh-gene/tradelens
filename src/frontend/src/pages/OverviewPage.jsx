import React from 'react'
import { apiGet } from '../apiClient.js'
import useApiResource from '../useApiResource.js'
import { formatPercent, formatScore } from '../formatters.js'
import { PageIntro, ResourceState, SetupCard } from '../components/PatternUi.jsx'

export default function OverviewPage({ onNavigate, onUnauthorized }) {
  const resource = useApiResource('overview', (signal) => apiGet('/api/overview?top=6', { signal, onUnauthorized }))
  return <ResourceState status={resource.status} error={resource.error} onRetry={resource.reload}>
    {resource.data && <>
      {resource.data.isStale && <div className="status-banner">This view is stale. Confirm the latest pattern scan before acting.</div>}
      <PageIntro eyebrow="Market overview" title="Evidence after the close." description="A ranked view of positional structures, market context, and lifecycle state." date={resource.data.dataAsOf} />
      <section className="freshness-card"><div><span>Pipeline</span><strong>{resource.data.pipeline.status}</strong></div><div><span>Securities scanned</span><strong>{resource.data.pipeline.securitiesScanned}</strong></div><div><span>Failed securities</span><strong>{resource.data.pipeline.failedSecurities}</strong></div></section>
      <section className="market-grid" aria-label="Market regime and lifecycle"><article className="regime-card"><p className="eyebrow">Market regime</p><div className="regime-score">{formatScore(resource.data.market.regimeScore)}</div><h2>{resource.data.market.label}</h2><p>{resource.data.market.benchmark}</p><dl><div><dt>Above EMA20</dt><dd>{formatPercent(resource.data.market.aboveEma20Pct)}</dd></div><div><dt>Above SMA50</dt><dd>{formatPercent(resource.data.market.aboveSma50Pct)}</dd></div><div><dt>Above SMA200</dt><dd>{formatPercent(resource.data.market.aboveSma200Pct)}</dd></div></dl></article><div className="state-counts">{Object.entries(resource.data.countsByState).map(([state, count]) => <button type="button" key={state} onClick={() => onNavigate(`/setups?state=${state}`)}><span>{state}</span><strong>{count}</strong><small>View setups →</small></button>)}</div></section>
      <section className="section-heading"><div><p className="eyebrow">Ranked opportunities</p><h2>Highest-ranked setups</h2></div><button type="button" className="secondary-button" onClick={() => onNavigate('/setups')}>Open screener</button></section>
      <p className="ranking-note">Ranking score, not historical probability. This is research evidence, not financial advice.</p>
      {resource.data.topSetups.length ? <div className="setup-grid">{resource.data.topSetups.map((setup) => <SetupCard key={setup.patternInstanceId} setup={setup} onNavigate={onNavigate} />)}</div> : <div className="empty-panel"><h2>No active opportunities</h2><p>The latest completed scan did not find setups matching the overview states.</p></div>}
    </>}
  </ResourceState>
}

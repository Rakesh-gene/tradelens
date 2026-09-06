import React, { useState } from 'react'
import { apiGet } from '../apiClient.js'
import useApiResource from '../useApiResource.js'
import { formatMarketDate, formatPercent, formatPrice } from '../formatters.js'
import { MeasurementGrid, PageIntro, ResourceState, Score, StateBadge } from '../components/PatternUi.jsx'
import PatternCandlestickChart from '../components/PatternCandlestickChart.jsx'

export default function PatternDetailPage({ patternId, onNavigate, onUnauthorized }) {
  const [chartRange, setChartRange] = useState('6m')
  const resource = useApiResource(`${patternId}:${chartRange}`, async (signal) => {
    const [detail, events, chart] = await Promise.all([
      apiGet(`/api/patterns/${patternId}`, { signal, onUnauthorized }),
      apiGet(`/api/patterns/${patternId}/events?pageSize=50`, { signal, onUnauthorized }),
      apiGet(`/api/patterns/${patternId}/chart?range=${chartRange}`, { signal, onUnauthorized }),
    ])
    return { pattern: detail.pattern, events: events.items, chart }
  })
  return <ResourceState status={resource.status} error={resource.error} onRetry={resource.reload}>{resource.data && (() => {
    const { pattern, events, chart } = resource.data
    const meaning = pattern.state === 'TRIGGERED' ? 'Price crossed the trigger level. Review the close against support before acting.' : pattern.state === 'CONFIRMED' ? 'The trigger has follow-through. Keep the invalidation level visible while managing risk.' : 'The setup is still forming. The trigger level is the price to watch.'
    const riskPct = pattern.pivotPrice && pattern.invalidationPrice ? (Number(pattern.pivotPrice) - Number(pattern.invalidationPrice)) / Number(pattern.pivotPrice) * 100 : null
    return <>
      <button type="button" className="text-button back-link" onClick={() => onNavigate('/setups')}>← Back to setups</button>
      <PageIntro eyebrow={pattern.patternClass} title={`${pattern.security.symbol || pattern.security.isin} · ${pattern.variant || pattern.patternType}`} description={pattern.security.name || pattern.patternType} date={pattern.lastUpdatedDate} />
      <section className="trade-brief evidence-card"><div className="card-title"><div><p className="eyebrow">At a glance</p><h2>{pattern.state === 'TRIGGERED' ? 'Breakout triggered' : `${pattern.state} setup`}</h2></div><StateBadge state={pattern.state} /></div><p className="trade-brief__meaning">{meaning}</p><div className="level-grid"><div><span>Last close</span><strong>{formatPrice(pattern.lastClose)}</strong></div><div><span>Trigger level</span><strong>{formatPrice(pattern.pivotPrice)}</strong><small>{pattern.triggerDate ? `Triggered ${formatMarketDate(pattern.triggerDate)}` : 'Watch for a decisive close above'}</small></div><div><span>Support</span><strong>{formatPrice(pattern.supportPrice)}</strong></div><div><span>Exit if invalidated</span><strong>{formatPrice(pattern.invalidationPrice)}</strong><small>{riskPct == null ? 'Risk not available' : `${formatPercent(riskPct)} below trigger`}</small></div></div></section>
      <section className="evidence-card"><PatternCandlestickChart candles={chart.candles} levels={chart.levels} markerDate={chart.markerDate} evidence={chart.evidence} range={chartRange} onRangeChange={setChartRange} /></section>
      <details className="evidence-card evidence-details"><summary>Open detailed evidence, scores and lifecycle</summary><section><h2>All detected signals ({pattern.allEvidence.length})</h2><div className="signal-evidence-list">{pattern.allEvidence.map((item) => { const hasTriggered = ['TRIGGERED', 'CONFIRMED'].includes(item.state); return <article key={item.patternInstanceId}><div><p className="eyebrow">{item.patternClass}</p><h3>{item.variant || item.patternType}</h3><StateBadge state={item.state} /></div><p>Detected {formatMarketDate(item.detectedDate)} · {hasTriggered ? `Triggered ${formatMarketDate(item.triggerDate)}` : 'Not triggered'}</p><dl><div><dt>Trigger</dt><dd>{formatPrice(item.pivotPrice)}</dd></div><div><dt>Support</dt><dd>{formatPrice(item.supportPrice)}</dd></div><div><dt>Invalidation</dt><dd>{formatPrice(item.invalidationPrice)}</dd></div></dl></article> })}</div></section><section className="detail-grid"><article><h2>Scores</h2><Score label="Setup" value={pattern.setupScore} /><Score label="Quality" value={pattern.qualityScore} /><Score label="Maturity" value={pattern.maturityScore} /><Score label="Context" value={pattern.contextScore} /><p className="ranking-note">Ranking score, not historical probability.</p></article><article><h2>Measured evidence</h2><MeasurementGrid values={pattern.measurements} /><details><summary>Scoring components</summary><MeasurementGrid values={{ ...pattern.scoreComponents.context, ...pattern.scoreComponents.setup }} /></details></article></section><section><h2>Lifecycle timeline</h2>{events.length ? <ol className="timeline">{events.map((event) => <li key={event.eventId}><span>{formatMarketDate(event.effectiveDate)}</span><strong>{event.eventType}</strong><p>{event.previousState || 'Created'} → {event.newState}</p><details><summary>Technical changes</summary><pre>{JSON.stringify(event.changes, null, 2)}</pre></details></li>)}</ol> : <p className="muted-copy">No lifecycle events recorded.</p>}</section></details>
      <section className="lineage"><span>Engine {pattern.lineage.engineVersion || '—'}</span><span>Configuration {pattern.lineage.configurationVersion || '—'}</span><span>Features {pattern.lineage.featureVersion || '—'}</span><span>Adjustments {pattern.lineage.adjustmentVersion || '—'}</span></section>
    </>
  })()}</ResourceState>
}

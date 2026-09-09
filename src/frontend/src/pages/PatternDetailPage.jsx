import React, { useState } from 'react'
import { getPattern, getPatternChart, getPatternEvents } from '../api/patternApi.js'
import useApiResource from '../useApiResource.js'
import { formatMarketDate, formatPercent, formatPrice } from '../utils/formatters.js'
import { MeasurementGrid, PageIntro, Score, StateBadge } from '../components/PatternUi.jsx'
import PatternCandlestickChart from '../components/PatternCandlestickChart.jsx'
import PatternTimeline from '../components/PatternTimeline.jsx'
import Breadcrumbs from '../components/Breadcrumbs.jsx'
import { ResourceState } from '../components/ResourceStates.jsx'
import useDocumentTitle from '../hooks/useDocumentTitle.js'
import PatternMeasurements from '../components/PatternMeasurements.jsx'
import SupportingPatternList from '../components/SupportingPatternList.jsx'

export default function PatternDetailPage({ patternId, onNavigate, onUnauthorized }) {
  useDocumentTitle('Pattern evidence')
  const [chartRange, setChartRange] = useState('6m')
  const resource = useApiResource(`${patternId}:${chartRange}`, async (signal) => {
    const [detail, events, chart] = await Promise.all([
      getPattern(patternId, { signal, onUnauthorized }),
      getPatternEvents(patternId, { pageSize: 50 }, { signal, onUnauthorized }),
      getPatternChart(patternId, { range: chartRange }, { signal, onUnauthorized }),
    ])
    return { pattern: detail.pattern, events: events.items, chart }
  })
  return <ResourceState status={resource.status} error={resource.error} onRetry={resource.reload}>{resource.data && (() => {
    const { pattern, events, chart } = resource.data
    const meaning = pattern.state === 'TRIGGERED' ? 'Price crossed the trigger level. Review the close against support before acting.' : pattern.state === 'CONFIRMED' ? 'The trigger has follow-through. Keep the invalidation level visible while managing risk.' : 'The setup is still forming. The trigger level is the price to watch.'
    const riskPct = pattern.pivotPrice && pattern.invalidationPrice ? (Number(pattern.pivotPrice) - Number(pattern.invalidationPrice)) / Number(pattern.pivotPrice) * 100 : null
    return <>
      <Breadcrumbs onNavigate={onNavigate} items={[{ label: 'Setups', to: '/setups' }, { label: pattern.security.symbol || pattern.security.isin, to: `/securities/${pattern.security.isin}` }, { label: pattern.variant || pattern.patternType }]} />
      <PageIntro eyebrow={pattern.patternClass} title={`${pattern.security.symbol || pattern.security.isin} · ${pattern.variant || pattern.patternType}`} description={pattern.security.name || pattern.patternType} date={pattern.lastUpdatedDate} />
      <section className="trade-brief evidence-card"><div className="card-title"><div><p className="eyebrow">At a glance</p><h2>{pattern.state === 'TRIGGERED' ? 'Breakout triggered' : `${pattern.state} setup`}</h2></div><StateBadge state={pattern.state} /></div><p className="trade-brief__meaning">{meaning}</p><div className="level-grid"><div><span>Last close</span><strong>{formatPrice(pattern.lastClose)}</strong></div><div><span>Trigger level</span><strong>{formatPrice(pattern.pivotPrice)}</strong><small>{pattern.triggerDate ? `Triggered ${formatMarketDate(pattern.triggerDate)}` : 'Watch for a decisive close above'}</small></div><div><span>Support</span><strong>{formatPrice(pattern.supportPrice)}</strong></div><div><span>Exit if invalidated</span><strong>{formatPrice(pattern.invalidationPrice)}</strong><small>{riskPct == null ? 'Risk not available' : `${formatPercent(riskPct)} below trigger`}</small></div></div></section>
      <section className="evidence-card"><PatternCandlestickChart candles={chart.candles} levels={chart.levels} markerDate={chart.markerDate} evidence={chart.evidence} corporateActions={chart.corporateActions} patternWindow={chart.patternWindow} range={chartRange} onRangeChange={setChartRange} /></section>
      <details className="evidence-card evidence-details"><summary>Open detailed evidence, scores and lifecycle</summary><section><h2>All detected signals ({pattern.allEvidence.length})</h2><div className="signal-evidence-list">{pattern.allEvidence.map((item) => { const hasTriggered = ['TRIGGERED', 'CONFIRMED'].includes(item.state); return <article key={item.patternInstanceId}><div><p className="eyebrow">{item.patternClass}</p><h3>{item.variant || item.patternType}</h3><StateBadge state={item.state} /></div><p>Detected {formatMarketDate(item.detectedDate)} · {hasTriggered ? `Triggered ${formatMarketDate(item.triggerDate)}` : 'Not triggered'}</p><dl><div><dt>Trigger</dt><dd>{formatPrice(item.pivotPrice)}</dd></div><div><dt>Support</dt><dd>{formatPrice(item.supportPrice)}</dd></div><div><dt>Invalidation</dt><dd>{formatPrice(item.invalidationPrice)}</dd></div></dl></article> })}</div></section><section><h2>Supporting evidence by family</h2><SupportingPatternList patterns={pattern.allEvidence} currentId={pattern.patternInstanceId} /></section><section className="detail-grid"><article><h2>Scores</h2><Score label="Setup" value={pattern.setupScore} /><Score label="Quality" value={pattern.qualityScore} /><Score label="Maturity" value={pattern.maturityScore} /><Score label="Context" value={pattern.contextScore} /><p className="ranking-note">Ranking score, not historical probability.</p></article><article><h2>Measured evidence</h2><PatternMeasurements patternType={pattern.patternType} values={pattern.measurements} /><details><summary>Scoring components</summary><MeasurementGrid values={{ ...pattern.scoreComponents.context, ...pattern.scoreComponents.setup }} /></details></article></section><section><h2>Lifecycle timeline</h2><PatternTimeline events={events} /></section></details>
      <section className="lineage"><span>Engine {pattern.lineage.engineVersion || '—'}</span><span>Configuration {pattern.lineage.configurationVersion || '—'}</span><span>Features {pattern.lineage.featureVersion || '—'}</span><span>Adjustments {pattern.lineage.adjustmentVersion || '—'}</span></section>
    </>
  })()}</ResourceState>
}

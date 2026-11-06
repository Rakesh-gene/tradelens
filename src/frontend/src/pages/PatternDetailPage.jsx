import React, { useState } from 'react'
import { getPattern, getPatternChart } from '../api/patternApi.js'
import useApiResource from '../useApiResource.js'
import { formatMarketDate } from '../utils/formatters.js'
import { PageIntro } from '../components/PatternUi.jsx'
import PatternCandlestickChart from '../components/PatternCandlestickChart.jsx'
import Breadcrumbs from '../components/Breadcrumbs.jsx'
import { ResourceState } from '../components/ResourceStates.jsx'
import useDocumentTitle from '../hooks/useDocumentTitle.js'
import DecisionSummary from '../components/DecisionSummary.jsx'
import { buildSecurityPath } from '../routing/routes.js'
import NavigationLink from '../components/NavigationLink.jsx'

export default function PatternDetailPage({ patternId, onNavigate, onUnauthorized }) {
  useDocumentTitle('Pattern evidence')
  const [chartRange, setChartRange] = useState('6m')
  const resource = useApiResource(`${patternId}:${chartRange}`, async (signal) => {
    const [detail, chart] = await Promise.all([
      getPattern(patternId, { signal, onUnauthorized }),
      getPatternChart(patternId, { range: chartRange }, { signal, onUnauthorized }),
    ])
    return { pattern: detail.pattern, freshness: detail, chart }
  })
  return <ResourceState status={resource.status} error={resource.error} onRetry={resource.reload}>{resource.data && (() => {
    const { pattern, freshness, chart } = resource.data
    return <>
      <Breadcrumbs onNavigate={onNavigate} items={[{ label: 'Setups', to: '/setups' }, { label: pattern.security.symbol, to: buildSecurityPath(pattern.security.symbol) }, { label: pattern.variant || pattern.patternType }]} />
      <PageIntro eyebrow="Pattern details" title={`${pattern.security.symbol || pattern.security.isin} · ${pattern.variant || pattern.patternType}`} description={`${pattern.security.name || pattern.patternType}. See the chart, key price levels, and signals behind this setup.`} date={pattern.lastUpdatedDate} dateLabel="Setup evidence as of" />
      <section className="evidence-card"><PatternCandlestickChart candles={chart.candles} levels={chart.levels} patternAnnotations={chart.patternAnnotations} markerDate={chart.markerDate} selectedPatternId={pattern.patternInstanceId} evidence={chart.evidence} corporateActions={chart.corporateActions} patternWindow={chart.patternWindow} range={chartRange} onRangeChange={setChartRange} /></section>
      <section className="trade-brief evidence-card"><div className="card-title"><h2>Decision intelligence</h2></div>{pattern.decision ? <DecisionSummary decision={pattern.decision} /> : <p className="muted-copy">Decision summary unavailable.</p>}</section>
      <footer className="setup-snapshot-footer" aria-label="Setup data freshness">
        <span>{freshness.hasNewerData ? `Latest analysis: ${formatMarketDate(freshness.latestDataAsOf)}` : freshness.isStale ? 'Stale setup snapshot' : 'Setup snapshot'}{pattern.terminalDate ? ` · ${pattern.state.toLowerCase()}` : ''}</span>
        <NavigationLink to={buildSecurityPath(pattern.security.symbol)} onNavigate={onNavigate}>Latest {pattern.security.symbol} chart →</NavigationLink>
      </footer>
    </>
  })()}</ResourceState>
}

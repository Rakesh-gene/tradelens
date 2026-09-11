import React, { useMemo, useState } from 'react'
import { getSetups } from '../api/marketApi.js'
import useApiResource from '../useApiResource.js'
import useDocumentTitle from '../hooks/useDocumentTitle.js'
import { PageIntro, SetupCard } from '../components/PatternUi.jsx'
import { EmptyState, ResourceState } from '../components/ResourceStates.jsx'

const TIMEFRAMES = [{ value: 'daily', label: 'Daily', detail: 'Current end-of-day scanner' }, { value: 'weekly', label: 'Weekly', detail: 'Higher-timeframe scan' }, { value: 'monthly', label: 'Monthly', detail: 'Primary-cycle scan' }]
const LIBRARY = [['Bases & breakouts', ['VCP', 'Flat base', 'Cup & handle', 'Ascending triangle', 'Rectangle', '52-week high breakout']], ['Reversal', ['Double bottom', 'Double top', 'Head & shoulders', 'Inverse head & shoulders', 'Rounding bottom']], ['Harmonic', ['Gartley', 'Bat', 'Butterfly', 'Crab', 'AB=CD']], ['Continuation', ['Bull flag', 'Bear flag', 'Pennant', 'Wedge', 'Channel']]]

export default function PatternScannerPage({ onNavigate, onUnauthorized }) {
  useDocumentTitle('Pattern scanner')
  const initial = new URLSearchParams(window.location.search).get('timeframe')
  const [timeframe, setTimeframe] = useState(TIMEFRAMES.some((item) => item.value === initial) ? initial : 'daily')
  const query = useMemo(() => ({ pageSize: 25, sort: 'setupScore', direction: 'desc' }), [])
  const resource = useApiResource(`pattern-scanner:${timeframe}`, (signal) => timeframe === 'daily' ? getSetups(query, { signal, onUnauthorized }) : Promise.resolve({ items: [], totalCount: 0 }))
  const selectTimeframe = (value) => { setTimeframe(value); onNavigate(`/pattern-scanner?timeframe=${value}`, { replace: true }) }
  const isAvailable = timeframe === 'daily'
  return <>
    <PageIntro eyebrow="Pattern discovery" title="Pattern scanner" description="Find rule-based chart structures across the market, then inspect their price evidence." date={resource.data?.dataAsOf} />
    <section className="scanner-panel" aria-label="Pattern scanner controls"><div><p className="eyebrow">Timeframe</p><h2>Select a chart interval</h2></div><div className="scanner-tabs" role="tablist" aria-label="Chart timeframe">{TIMEFRAMES.map((item) => <button key={item.value} type="button" role="tab" aria-selected={timeframe === item.value} className={timeframe === item.value ? 'is-active' : ''} onClick={() => selectTimeframe(item.value)}><strong>{item.label}</strong><small>{item.detail}</small></button>)}</div></section>
    <section className="scanner-library" aria-labelledby="pattern-library-title"><div className="section-heading"><div><p className="eyebrow">Detection library</p><h2 id="pattern-library-title">Structures to scan</h2></div><p>Daily detection is live. Weekly and monthly aggregation, plus reversal and harmonic detectors, will appear after server-side validation.</p></div><div className="scanner-library__grid">{LIBRARY.map(([family, patterns]) => <article key={family}><h3>{family}</h3><div className="tag-list">{patterns.map((pattern) => <span key={pattern}>{pattern}</span>)}</div></article>)}</div></section>
    {!isAvailable && <section className="scanner-empty evidence-card"><p className="eyebrow">{timeframe} scan</p><h2>Not processed yet</h2><p>TradeLens currently persists daily bars and daily pattern evidence. Weekly and monthly results need server-side aggregation and detectors so every signal remains reproducible.</p></section>}
    {isAvailable && <ResourceState status={resource.status} error={resource.error} onRetry={resource.reload}>{resource.data && <section aria-labelledby="daily-results"><div className="section-heading"><div><p className="eyebrow">Daily scan</p><h2 id="daily-results">Detected market structures</h2></div><p>{resource.data.totalCount || 0} active patterns ranked by setup score.</p></div>{resource.data.items?.length ? <div className="setup-grid">{resource.data.items.map((setup) => <SetupCard key={setup.patternInstanceId} setup={setup} onNavigate={onNavigate} />)}</div> : <EmptyState title="No active daily patterns" message="Run the market pipeline or choose another market date in Setups." />}</section>}</ResourceState>}
  </>
}

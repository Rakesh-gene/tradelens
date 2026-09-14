import { useEffect } from 'react'
import { getIndices } from '../api/indicesApi.js'
import useApiResource from '../useApiResource.js'
import useDocumentTitle from '../hooks/useDocumentTitle.js'
import { EmptyState, ResourceState } from '../components/ResourceStates.jsx'
import { PageIntro, StateBadge } from '../components/PatternUi.jsx'
import NavigationLink from '../components/NavigationLink.jsx'
import { buildPatternPath, buildSecurityPath } from '../routing/routes.js'
import { formatMarketDate, formatNumber, formatPercent, formatPrice, formatScore, labelize } from '../utils/formatters.js'
import { normalizeIndexView, readIndexView, saveIndexView } from '../indexPreferences.js'

const CATEGORY_LABELS = { BROAD_MARKET: 'Broad market', SECTORAL: 'Sectoral', THEMATIC: 'Thematic' }
const ZONE_LABELS = { LEADING: 'Leading', WEAKENING: 'Weakening', LAGGING: 'Lagging', IMPROVING: 'Improving', UNAVAILABLE: 'Insufficient history' }

function ViewSwitch({ view, onChange }) {
  return <div className="watchlist-view-switch" role="group" aria-label="Index layout">
    <button type="button" aria-pressed={view === 'cards'} onClick={() => onChange('cards')}>Cards</button>
    <button type="button" aria-pressed={view === 'list'} onClick={() => onChange('list')}>List</button>
    <button type="button" aria-pressed={view === 'quadrant'} onClick={() => onChange('quadrant')}>Quadrant</button>
  </div>
}

function TrendSummary({ trend }) {
  const values = Object.values(trend || {}).filter((value) => value != null)
  return values.length ? `${values.filter(Boolean).length}/${values.length} above averages` : 'Trend unavailable'
}

function IndexCard({ item, onNavigate }) {
  const setup = item.primarySetup
  return <article className="watchlist-card index-card">
    <header className="watchlist-card__head"><div><p className="eyebrow">{CATEGORY_LABELS[item.category] || labelize(item.category)}</p><NavigationLink to={buildSecurityPath(item.engineSecurityId)} onNavigate={onNavigate}><h3>{item.name}</h3></NavigationLink><small>{item.code}</small></div>{setup && <StateBadge state={setup.state} />}</header>
    <div className="watchlist-price"><div><small>Last close</small><strong>{formatPrice(item.lastClose)}</strong></div><span className={Number(item.dailyChangePct) >= 0 ? 'is-positive' : 'is-negative'}>{formatPercent(item.dailyChangePct, { signed: true })}</span></div>
    <div className="watchlist-context"><span>{TrendSummary({ trend: item.trend })}</span><span>52-week high <strong>{formatPercent(item.distanceTo52WeekHighPct, { signed: true })}</strong></span></div>
    <dl className="watchlist-rs"><div><dt>1M RS</dt><dd>{formatPercent(item.relativeStrength1m, { signed: true })}</dd></div><div><dt>3M RS</dt><dd>{formatPercent(item.relativeStrength3m, { signed: true })}</dd></div><div><dt>6M RS</dt><dd>{formatPercent(item.relativeStrength6m, { signed: true })}</dd></div><div><dt>12M RS</dt><dd>{formatPercent(item.relativeStrength12m, { signed: true })}</dd></div></dl>
    {setup ? <div className="watchlist-setup"><div><span>Primary setup</span><NavigationLink to={buildPatternPath(setup.patternInstanceId)} onNavigate={onNavigate}>{setup.variant || setup.patternType}</NavigationLink><strong>Score {formatScore(setup.setupScore)}</strong></div><dl><div><dt>To pivot</dt><dd>{formatPercent(setup.distanceToPivotPct, { signed: true })}</dd></div><div><dt>Pivot</dt><dd>{formatPrice(setup.pivotPrice)}</dd></div></dl></div> : <p className="muted-copy">No active daily setup.</p>}
    <footer><small>Data as of {formatMarketDate(item.dataAsOf)}</small></footer>
  </article>
}

function IndexRow({ item, onNavigate }) {
  const setup = item.primarySetup
  return <article className="watchlist-row index-row" role="listitem">
    <div className="watchlist-row__security"><NavigationLink to={buildSecurityPath(item.engineSecurityId)} onNavigate={onNavigate}>{item.name}</NavigationLink><span>{CATEGORY_LABELS[item.category] || labelize(item.category)}</span></div>
    <div className="watchlist-row__metric"><small>Last close</small><strong>{formatPrice(item.lastClose)}</strong><span>{formatPercent(item.dailyChangePct, { signed: true })}</span></div>
    <div className="watchlist-row__metric"><small>Trend</small><strong>{TrendSummary({ trend: item.trend })}</strong></div>
    <div className="watchlist-row__metric"><small>3M RS</small><strong>{formatPercent(item.relativeStrength3m, { signed: true })}</strong><span>{ZONE_LABELS[item.rotation?.zone]}</span></div>
    <div className="watchlist-row__setup"><small>Primary setup</small>{setup ? <><NavigationLink to={buildPatternPath(setup.patternInstanceId)} onNavigate={onNavigate}>{setup.variant || setup.patternType}</NavigationLink><span>Score {formatScore(setup.setupScore)}</span></> : <strong>None active</strong>}</div>
    <div className="watchlist-row__state">{setup && <StateBadge state={setup.state} />}</div>
  </article>
}

function IndexQuadrant({ items, onNavigate }) {
  const plotted = items.filter((item) => item.rotation?.strength != null && item.rotation?.momentum != null)
  const xMax = Math.max(1, ...plotted.map((item) => Math.abs(Number(item.rotation.strength)))) * 1.15
  const yMax = Math.max(1, ...plotted.map((item) => Math.abs(Number(item.rotation.momentum)))) * 1.15
  const open = (item) => onNavigate(buildSecurityPath(item.engineSecurityId))
  return <section className="watchlist-quadrant"><header><div><h2>NSE index rotation</h2><p>Relative strength and momentum versus NIFTY 500.</p></div><span>{plotted.length}/{items.length} plotted</span></header>
    {plotted.length ? <><div className="rotation-axis-title">↑ RS momentum proxy (pp)</div><div className="rotation-plot" role="group" aria-label="NSE index relative strength quadrants">
      <div className="rotation-zone rotation-zone--improving">Improving</div><div className="rotation-zone rotation-zone--leading">Leading</div><div className="rotation-zone rotation-zone--lagging">Lagging</div><div className="rotation-zone rotation-zone--weakening">Weakening</div><span className="rotation-origin">0</span>
      {plotted.map((item, index) => <button key={item.code} className="rotation-point watchlist-quadrant__point" style={{ left: `${50 + Number(item.rotation.strength) / xMax * 44}%`, top: `${50 - Number(item.rotation.momentum) / yMax * 44}%` }} onClick={() => open(item)} aria-label={`${item.name}: ${ZONE_LABELS[item.rotation.zone]}, RS ${formatNumber(item.rotation.strength)}, momentum ${formatNumber(item.rotation.momentum)}`}>{index + 1}</button>)}
    </div><div className="rotation-axis-title">3-month relative strength (pp) →</div><div className="watchlist-quadrant__legend" role="list">{plotted.map((item, index) => <div role="listitem" key={item.code}><button onClick={() => open(item)}><span>{index + 1}</span><strong>{item.name}</strong><span>{ZONE_LABELS[item.rotation.zone]}</span><span>{formatNumber(item.rotation.strength)} pp RS</span><span>{formatNumber(item.rotation.momentum)} pp momentum</span></button></div>)}</div></> : <EmptyState title="Index rotation is not available yet" message="Run the index pipeline to import enough benchmark-aligned history." />}
  </section>
}

function IndexActivityFeed({ activity, onNavigate }) {
  return <aside className="watchlist-activity" aria-labelledby="index-activity-title"><div><p className="eyebrow">Index feed</p><h2 id="index-activity-title">Recent activity</h2></div>
    {activity.length ? <ol>{activity.map((event) => <li key={event.eventId}>
      <time dateTime={event.effectiveDate}>{formatMarketDate(event.effectiveDate)}</time>
      <NavigationLink to={buildSecurityPath(event.index.engineSecurityId)} onNavigate={onNavigate}>{event.index.name || event.index.code}</NavigationLink>
      {event.activityType === 'QUADRANT' ? <>
        <p>{event.eventType === 'QUADRANT_ENTERED' ? `Entered ${ZONE_LABELS[event.newZone] || labelize(event.newZone)} quadrant` : event.eventType === 'QUADRANT_LEFT' ? `Left ${ZONE_LABELS[event.previousZone] || labelize(event.previousZone)} quadrant` : `${ZONE_LABELS[event.previousZone] || labelize(event.previousZone)} → ${ZONE_LABELS[event.newZone] || labelize(event.newZone)}`}</p>
        <small>3M RS {formatNumber(event.strength)} pp · Momentum {formatNumber(event.momentum)} pp</small>
      </> : <>
        <p>{labelize(event.eventType)} · {event.previousState ? `${labelize(event.previousState)} → ` : ''}{labelize(event.newState)}</p>
        <small>{event.variant || event.patternType}</small>
      </>}
    </li>)}</ol> : <p className="muted-copy">Pattern and quadrant changes will appear after the next completed index scan.</p>}
  </aside>
}

export default function IndicesPage({ onNavigate, onUnauthorized }) {
  useDocumentTitle('NSE indices')
  const resource = useApiResource('indices', (signal) => getIndices({ signal, onUnauthorized }))
  const requested = new URLSearchParams(window.location.search).get('view')
  const valid = ['cards', 'list', 'quadrant'].includes(requested)
  const view = valid ? normalizeIndexView(requested) : readIndexView()
  useEffect(() => { if (valid) saveIndexView(requested) }, [valid, requested])
  const changeView = (next) => { const saved = saveIndexView(next); const query = new URLSearchParams(window.location.search); query.set('view', saved); onNavigate(`/indices?${query}`) }
  const data = resource.data
  return <><PageIntro eyebrow="Market benchmarks" title="NSE indices" description="Follow broad-market, sector, and thematic NIFTY indices and see where strength is building or fading." date={data?.dataAsOf} />
    {data && <div className="watchlist-toolbar"><div className="watchlist-summary"><strong>{data.count}<small>indices tracked</small></strong>{data.categories.map((category) => <span key={category.id}>{CATEGORY_LABELS[category.id]} <b>{category.count}</b></span>)}</div><ViewSwitch view={view} onChange={changeView} /></div>}
    {data?.isStale && <p className="status-banner">Index data is stale or the initial ten-year import is incomplete.</p>}
    <ResourceState status={resource.status} error={resource.error} onRetry={resource.reload}>{data && (data.items.length ? <div className="watchlist-layout"><main className="watchlist-groups">{view === 'quadrant' ? <IndexQuadrant items={data.items} onNavigate={onNavigate} /> : data.categories.filter((category) => category.count).map((category) => <section className="watchlist-group" key={category.id}><header><div><h2>{CATEGORY_LABELS[category.id]}</h2><p>{category.id === 'BROAD_MARKET' ? 'Market-cap and size benchmarks.' : category.id === 'SECTORAL' ? 'Industry and sector benchmarks.' : 'Theme and strategy benchmarks.'}</p></div><span>{category.count}</span></header><div className={view === 'list' ? 'watchlist-list' : 'watchlist-grid'} role={view === 'list' ? 'list' : undefined}>{category.items.map((item) => view === 'list' ? <IndexRow key={item.code} item={item} onNavigate={onNavigate} /> : <IndexCard key={item.code} item={item} onNavigate={onNavigate} />)}</div></section>)}</main><IndexActivityFeed activity={data.activity || []} onNavigate={onNavigate} /></div> : <EmptyState title="No index data yet" message="Index analysis will appear here after the first market-data update is complete." />)}</ResourceState>
    {data && <details className="methodology-note"><summary>Index methodology</summary><p>{data.methodology}</p></details>}
  </>
}

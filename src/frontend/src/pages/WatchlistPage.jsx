import { useEffect, useState } from 'react'
import { getWatchlist, removeFromWatchlist } from '../api/watchlistApi.js'
import useApiResource from '../useApiResource.js'
import useDocumentTitle from '../hooks/useDocumentTitle.js'
import { EmptyState, ResourceState } from '../components/ResourceStates.jsx'
import { PageIntro, StateBadge } from '../components/PatternUi.jsx'
import NavigationLink from '../components/NavigationLink.jsx'
import { buildPatternPath, buildSecurityPath } from '../routing/routes.js'
import { formatMarketDate, formatNumber, formatPercent, formatPrice, formatScore, labelize } from '../utils/formatters.js'
import { normalizeWatchlistView, readWatchlistView, saveWatchlistView } from '../watchlistPreferences.js'

const GROUP_COPY = {
  ACTION_REQUIRED: ['Action required', 'Triggered and confirmed setups that need review.'],
  NEAR_BREAKOUT: ['Near breakout', 'Ready setups trading within 3% below their pivot.'],
  DEVELOPING: ['Developing', 'Active structures that are still forming or maturing.'],
  WEAKENING: ['Weakening', 'Stocks losing trend or relative-strength support.'],
  NO_ACTIVE_SETUP: ['No active setup', 'Watched stocks without an active daily setup.'],
}

function TrendMark({ label, value }) {
  const text = value == null ? 'Unavailable' : value ? 'Above' : 'Below'
  return <span className={`watchlist-trend ${value == null ? 'is-unknown' : value ? 'is-positive' : 'is-negative'}`}><small>{label}</small>{text}</span>
}

function WatchlistCard({ item, onNavigate, onRemove, removing }) {
  const setup = item.primarySetup
  return <article className="watchlist-card">
    <header className="watchlist-card__head">
      <div><NavigationLink to={buildSecurityPath(item.security.isin)} onNavigate={onNavigate}><h3>{item.security.symbol || item.security.isin}</h3></NavigationLink><p>{item.security.name}</p><small>{item.security.sectorName || 'Sector unavailable'}</small></div>
      {setup && <StateBadge state={setup.state} />}
    </header>
    <div className="watchlist-price"><div><small>Last close</small><strong>{formatPrice(item.lastClose)}</strong></div><span className={Number(item.dailyChangePct) >= 0 ? 'is-positive' : 'is-negative'}>{formatPercent(item.dailyChangePct, { signed: true })} today</span></div>
    <div className="watchlist-trends" aria-label="Moving-average trend">
      <TrendMark label="EMA20" value={item.trend?.aboveEma20} /><TrendMark label="SMA50" value={item.trend?.aboveSma50} /><TrendMark label="SMA200" value={item.trend?.aboveSma200} />
    </div>
    <dl className="watchlist-rs"><div><dt>1M RS</dt><dd>{formatPercent(item.relativeStrength1m)}</dd></div><div><dt>3M RS</dt><dd>{formatPercent(item.relativeStrength3m)}</dd></div><div><dt>6M RS</dt><dd>{formatPercent(item.relativeStrength6m)}</dd></div><div><dt>12M RS</dt><dd>{formatPercent(item.relativeStrength12m)}</dd></div></dl>
    <div className="watchlist-context"><span>52-week high <strong>{formatPercent(item.distanceTo52WeekHighPct, { signed: true })}</strong></span><span>Sector RS <strong>{formatPercent(item.sectorContext?.relativeStrength, { signed: true })}</strong></span><span>RS percentile <strong>{formatNumber(item.relativeStrengthPercentile)}</strong></span></div>
    {setup ? <div className="watchlist-setup">
      <div><span>Primary setup</span><NavigationLink to={buildPatternPath(setup.patternInstanceId)} onNavigate={onNavigate}>{setup.variant || setup.patternType}</NavigationLink><strong>Score {formatScore(setup.setupScore)}</strong></div>
      <dl><div><dt>To pivot</dt><dd>{formatPercent(setup.distanceToPivotPct, { signed: true })}</dd></div><div><dt>Pivot</dt><dd>{formatPrice(setup.pivotPrice)}</dd></div><div><dt>Support</dt><dd>{formatPrice(setup.supportPrice)}</dd></div><div><dt>Invalidation</dt><dd>{formatPrice(setup.invalidationPrice)}</dd></div></dl>
    </div> : <p className="muted-copy">No active primary setup.</p>}
    <footer><small>Data as of {formatMarketDate(item.dataAsOf)}</small><button className="secondary-button" type="button" disabled={removing} onClick={() => onRemove(item.security.isin)}>{removing ? 'Removing…' : 'Remove'}</button></footer>
  </article>
}

function WatchlistRow({ item, onNavigate, onRemove, removing }) {
  const setup = item.primarySetup
  const knownTrends = Object.values(item.trend || {}).filter((value) => value != null)
  const aboveTrends = knownTrends.filter(Boolean).length
  return <article className="watchlist-row" role="listitem">
    <div className="watchlist-row__security"><NavigationLink to={buildSecurityPath(item.security.isin)} onNavigate={onNavigate}>{item.security.symbol || item.security.isin}</NavigationLink><span>{item.security.name}</span><small>{item.security.sectorName || 'Sector unavailable'}</small></div>
    <div className="watchlist-row__metric"><small>Last close</small><strong>{formatPrice(item.lastClose)}</strong><span className={Number(item.dailyChangePct) >= 0 ? 'is-positive' : 'is-negative'}>{formatPercent(item.dailyChangePct, { signed: true })}</span></div>
    <div className="watchlist-row__metric"><small>Trend</small><strong>{knownTrends.length ? `${aboveTrends}/${knownTrends.length} above` : 'Unavailable'}</strong><span>EMA20 · SMA50 · SMA200</span></div>
    <div className="watchlist-row__metric"><small>3M stock RS</small><strong>{formatPercent(item.relativeStrength3m, { signed: true })}</strong><span>Percentile {formatNumber(item.relativeStrengthPercentile)}</span></div>
    <div className="watchlist-row__metric"><small>Sector RS</small><strong>{formatPercent(item.sectorContext?.relativeStrength, { signed: true })}</strong><span>3-month median</span></div>
    <div className="watchlist-row__setup"><small>Primary setup</small>{setup ? <><NavigationLink to={buildPatternPath(setup.patternInstanceId)} onNavigate={onNavigate}>{setup.variant || setup.patternType}</NavigationLink><span>{formatPercent(setup.distanceToPivotPct, { signed: true })} to pivot</span></> : <strong>None active</strong>}</div>
    <div className="watchlist-row__state">{setup && <StateBadge state={setup.state} />}<button type="button" aria-label={`Remove ${item.security.symbol || item.security.isin} from watchlist`} disabled={removing} onClick={() => onRemove(item.security.isin)}>{removing ? '…' : 'Remove'}</button></div>
  </article>
}

function ViewSwitch({ view, onChange }) {
  return <div className="watchlist-view-switch" role="group" aria-label="Watchlist layout">
    <button type="button" aria-pressed={view === 'cards'} onClick={() => onChange('cards')}><span aria-hidden="true">▦</span> Cards</button>
    <button type="button" aria-pressed={view === 'list'} onClick={() => onChange('list')}><span aria-hidden="true">☷</span> List</button>
    <button type="button" aria-pressed={view === 'quadrant'} onClick={() => onChange('quadrant')}><span aria-hidden="true">⌖</span> Quadrant</button>
  </div>
}

const ZONE_LABELS = { LEADING: 'Leading', WEAKENING: 'Weakening', LAGGING: 'Lagging', IMPROVING: 'Improving', UNAVAILABLE: 'Insufficient history' }

function WatchlistQuadrant({ items, onNavigate }) {
  const plotted = items.filter((item) => item.rotation?.strength != null && item.rotation?.momentum != null)
  const xMax = Math.max(1, ...plotted.map((item) => Math.abs(Number(item.rotation.strength)))) * 1.15
  const yMax = Math.max(1, ...plotted.map((item) => Math.abs(Number(item.rotation.momentum)))) * 1.15
  return <section className="watchlist-quadrant" aria-labelledby="watchlist-quadrant-title">
    <header><div><h2 id="watchlist-quadrant-title">Watchlist rotation</h2><p>Compare the direction and pace of benchmark-relative strength across your stocks.</p></div><span>{plotted.length}/{items.length} plotted</span></header>
    {plotted.length ? <>
      <div className="rotation-axis-title">↑ RS momentum proxy (pp): accelerating above zero</div>
      <div className="rotation-plot" role="group" aria-label="Watchlist stock relative strength quadrants">
        <div className="rotation-zone rotation-zone--improving">Improving</div><div className="rotation-zone rotation-zone--leading">Leading</div>
        <div className="rotation-zone rotation-zone--lagging">Lagging</div><div className="rotation-zone rotation-zone--weakening">Weakening</div><span className="rotation-origin">0</span>
        {plotted.map((item, index) => <button key={item.security.isin} className="rotation-point watchlist-quadrant__point" style={{ left: `${50 + Number(item.rotation.strength) / xMax * 44}%`, top: `${50 - Number(item.rotation.momentum) / yMax * 44}%` }} onClick={() => onNavigate(buildSecurityPath(item.security.isin))} aria-label={`${item.security.symbol}: ${ZONE_LABELS[item.rotation.zone]}, 3-month RS ${formatNumber(item.rotation.strength)} percentage points, momentum ${formatNumber(item.rotation.momentum)} percentage points`} title={`${item.security.symbol}: ${ZONE_LABELS[item.rotation.zone]}`}>{index + 1}</button>)}
      </div>
      <div className="rotation-mobile" aria-label="Watchlist stock zones on mobile">{['IMPROVING', 'LEADING', 'LAGGING', 'WEAKENING'].map((zone) => <section className={`rotation-mobile-zone rotation-zone--${zone.toLowerCase()}`} key={zone}><h3>{ZONE_LABELS[zone]}</h3>{plotted.filter((item) => item.rotation.zone === zone).map((item) => <button className="secondary-button" key={item.security.isin} onClick={() => onNavigate(buildSecurityPath(item.security.isin))}>{item.security.symbol}<small>{formatPercent(item.rotation.strength, { signed: true })}</small></button>)}</section>)}</div>
      <div className="rotation-axis-title">3-month relative strength (pp) →</div>
      <div className="watchlist-quadrant__legend" role="list" aria-label="Watchlist quadrant values">{plotted.map((item, index) => <div role="listitem" key={item.security.isin}><button onClick={() => onNavigate(buildSecurityPath(item.security.isin))}><span>{index + 1}</span><strong>{item.security.symbol}</strong><span>{ZONE_LABELS[item.rotation.zone]}</span><span>{formatNumber(item.rotation.strength)} pp RS</span><span>{formatNumber(item.rotation.momentum)} pp momentum</span></button></div>)}</div>
    </> : <p className="muted-copy">At least one month of benchmark-relative history is required before a stock can be plotted.</p>}
    <details><summary>How the quadrant is calculated</summary><p>X is 3-month benchmark-relative return. Y is 1-month RS minus one-third of 3-month RS. Zero divides each axis. This is a momentum proxy and ranking aid, not a forecast or trade recommendation.</p></details>
  </section>
}

function ActivityFeed({ activity, onNavigate }) {
  return <aside className="watchlist-activity" aria-labelledby="watchlist-activity-title"><div><p className="eyebrow">Change feed</p><h2 id="watchlist-activity-title">Recent activity</h2></div>
    {activity.length ? <ol>{activity.map((event) => <li key={event.eventId}>
      <time dateTime={event.effectiveDate}>{formatMarketDate(event.effectiveDate)}</time>
      <NavigationLink to={buildSecurityPath(event.security.isin)} onNavigate={onNavigate}>{event.security.symbol || event.security.isin}</NavigationLink>
      {event.activityType === 'QUADRANT' ? <>
        <p>{event.eventType === 'QUADRANT_ENTERED' ? `Entered ${labelize(event.newZone)} quadrant` : event.eventType === 'QUADRANT_LEFT' ? `Left ${labelize(event.previousZone)} quadrant` : `${labelize(event.previousZone)} → ${labelize(event.newZone)}`}</p>
        <small>3M RS {formatNumber(event.strength)} pp · Momentum {formatNumber(event.momentum)} pp</small>
      </> : <><p>{labelize(event.eventType)} · {event.previousState ? `${labelize(event.previousState)} → ` : ''}{labelize(event.newState)}</p><small>{event.variant || event.patternType}</small></>}
    </li>)}</ol> : <p className="muted-copy">Pattern and quadrant changes for watched stocks will appear after the next completed scan.</p>}
  </aside>
}

export default function WatchlistPage({ onNavigate, onUnauthorized, revision = 0 }) {
  useDocumentTitle('Watchlist')
  const resource = useApiResource(`watchlist:${revision}`, (signal) => getWatchlist({ signal, onUnauthorized }))
  const [removing, setRemoving] = useState('')
  const [error, setError] = useState('')
  const requestedView = new URLSearchParams(window.location.search).get('view')
  const hasValidRequestedView = ['cards', 'list', 'quadrant'].includes(requestedView)
  const view = hasValidRequestedView ? normalizeWatchlistView(requestedView) : readWatchlistView()
  useEffect(() => {
    if (hasValidRequestedView) saveWatchlistView(requestedView)
  }, [hasValidRequestedView, requestedView])
  const changeView = (nextView) => {
    const savedView = saveWatchlistView(nextView)
    const query = new URLSearchParams(window.location.search)
    query.set('view', savedView)
    onNavigate(`/watchlist?${query.toString()}`)
  }
  const remove = async (isin) => {
    setRemoving(isin); setError('')
    try { await removeFromWatchlist(isin, { onUnauthorized }); resource.reload() }
    catch (requestError) { setError(requestError.message || 'Could not remove this stock.') }
    finally { setRemoving('') }
  }
  const data = resource.data
  return <>
    <PageIntro eyebrow="Your stocks" title="Watchlist" description="Keep an eye on price trend, relative strength, and active setups for the stocks you follow." date={data?.dataAsOf} />
    {data && <div className="watchlist-toolbar"><div className="watchlist-summary" aria-label="Watchlist summary"><strong>{data.count}<small>of {data.limit} saved</small></strong>{data.groups.map((group) => <span key={group.id}>{GROUP_COPY[group.id]?.[0] || labelize(group.id)} <b>{group.count}</b></span>)}</div><ViewSwitch view={view} onChange={changeView} /></div>}
    {data?.isStale && <p className="status-banner">Market data is stale.</p>}
    {error && <p className="status-banner" role="alert">{error}</p>}
    <ResourceState status={resource.status} error={resource.error} onRetry={resource.reload}>
      {data && (data.items.length ? <div className="watchlist-layout"><main className="watchlist-groups">
        {view === 'quadrant' ? <WatchlistQuadrant items={data.items} onNavigate={onNavigate} /> : data.groups.filter((group) => group.count).map((group) => <section key={group.id} className={`watchlist-group watchlist-group--${group.id.toLowerCase().replaceAll('_', '-')}`}><header><div><h2>{GROUP_COPY[group.id]?.[0] || labelize(group.id)}</h2><p>{GROUP_COPY[group.id]?.[1]}</p></div><span>{group.count}</span></header><div className={view === 'list' ? 'watchlist-list' : 'watchlist-grid'} role={view === 'list' ? 'list' : undefined}>{group.items.map((item) => view === 'list' ? <WatchlistRow key={item.security.isin} item={item} onNavigate={onNavigate} onRemove={remove} removing={removing === item.security.isin} /> : <WatchlistCard key={item.security.isin} item={item} onNavigate={onNavigate} onRemove={remove} removing={removing === item.security.isin} />)}</div></section>)}
      </main><ActivityFeed activity={data.activity || []} onNavigate={onNavigate} /></div> : <EmptyState title="Your watchlist is empty" message="Open a stock from search, setups, or sector rotation and add it to your watchlist." />)}
    </ResourceState>
  </>
}

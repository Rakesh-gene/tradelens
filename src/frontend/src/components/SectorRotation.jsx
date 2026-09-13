import React from 'react'
import { getSectorRotation, getSectorStocks } from '../api/marketApi.js'
import useApiResource from '../useApiResource.js'
import { EmptyState, ResourceState } from './ResourceStates.jsx'
import NavigationLink from './NavigationLink.jsx'
import { buildSecurityPath } from '../routing/routes.js'
import { formatNumber } from '../utils/formatters.js'

const number = (value) => value == null ? 'Unavailable' : `${formatNumber(value)} pp`
const labels = { LEADING: 'Leading', WEAKENING: 'Weakening', LAGGING: 'Lagging', IMPROVING: 'Improving', UNAVAILABLE: 'Insufficient history' }

function SectorStocks({ sector, asOf, onUnauthorized, onNavigate }) {
  const cursor = new URLSearchParams(window.location.search).get('sectorCursor')
  const setCursor = (value) => {
    const query = new URLSearchParams(window.location.search)
    if (value) query.set('sectorCursor', value)
    else query.delete('sectorCursor')
    onNavigate(`/sector-rotation?${query}`)
  }
  const resource = useApiResource(`${sector.code}:${asOf}:${cursor}`, (signal) => getSectorStocks({ sector: sector.code, asOf, cursor }, { signal, onUnauthorized }))
  return <section className="sector-stock-list" aria-label={`${sector.name} stocks`}>
    <h3>{sector.name} — stocks by strength</h3>
    <p>Ranked by 3-month benchmark-relative return. As of {asOf}. Missing values remain unranked.</p>
    <ResourceState status={resource.status} error={resource.error} onRetry={resource.reload}>
      {resource.status === 'success' && resource.data && <>
        {resource.data.items.length ? <ol className="sector-stock-rows">{resource.data.items.map((item) => <li key={item.security.isin}>
          <span className="sector-stock-rank">{item.rank ?? '—'}</span>
          <NavigationLink to={buildSecurityPath(item.security.isin)} onNavigate={onNavigate}>{item.security.symbol}<small>{item.security.name}</small></NavigationLink>
          <strong>{number(item.rs3m)}</strong>
        </li>)}</ol> : <EmptyState title="No stocks available" message="No classified equities are available for this sector and date." />}
        <div className="sector-pagination">{cursor && <button className="secondary-button" onClick={() => setCursor(null)}>First page</button>}{resource.data.nextCursor && <button className="secondary-button" onClick={() => setCursor(resource.data.nextCursor)}>Next 25 stocks</button>}</div>
      </>}
    </ResourceState>
  </section>
}

export default function SectorRotation({ onUnauthorized, onNavigate }) {
  const query = new URLSearchParams(window.location.search)
  const asOf = query.get('asOf')
  const resource = useApiResource(`sector-rotation:${asOf}`, (signal) => getSectorRotation({ asOf }, { signal, onUnauthorized }))
  const selected = query.get('sector')
  const setSelected = (code) => {
    const next = new URLSearchParams(window.location.search)
    next.set('sector', code)
    next.delete('sectorCursor')
    if (resource.data?.dataAsOf) next.set('asOf', resource.data.dataAsOf)
    onNavigate(`/sector-rotation?${next}`)
  }
  const data = resource.data
  const items = data?.items || []
  const plotted = items.filter((item) => item.rs3m != null && item.momentum != null)
  const xMax = Math.max(1, ...plotted.map((item) => Math.abs(item.rs3m))) * 1.15
  const yMax = Math.max(1, ...plotted.map((item) => Math.abs(item.momentum))) * 1.15
  const chosen = items.find((item) => item.code === selected)
  return <section className="sector-rotation" aria-labelledby="sector-rotation-title">
    <h2 id="sector-rotation-title">Sector rotation</h2>
    <p>See which sectors are gaining or losing relative strength. Select a sector to explore its strongest stocks.</p>
    <ResourceState status={resource.status} error={resource.error} onRetry={resource.reload}>
      {data && <>
        <p>End of day: {data.dataAsOf || 'Unavailable'} · Momentum proxy: 1M RS − 3M RS / 3{data.isStale && ' · Stale data'}</p>
        {!items.length ? <EmptyState title="Sector strength is not available yet" message="Sector classifications and benchmark-aligned technical features are needed." /> : <>
          <div className="rotation-axis-title">↑ RS momentum proxy (pp): accelerating above zero</div>
          <div className="rotation-plot" role="group" aria-label="Sector relative strength and momentum quadrants">
            <div className="rotation-zone rotation-zone--improving">Improving</div><div className="rotation-zone rotation-zone--leading">Leading</div>
            <div className="rotation-zone rotation-zone--lagging">Lagging</div><div className="rotation-zone rotation-zone--weakening">Weakening</div>
            <span className="rotation-origin">0</span>
            {plotted.map((item, index) => <button key={item.code} className={`rotation-point${selected === item.code ? ' is-selected' : ''}`} style={{ left: `${50 + Number(item.rs3m) / xMax * 44}%`, top: `${50 - Number(item.momentum) / yMax * 44}%` }} onClick={() => setSelected(item.code)} aria-pressed={selected === item.code} aria-label={`${item.name}: ${labels[item.zone]}, RS ${number(item.rs3m)}, momentum ${number(item.momentum)}`} title={`${item.name}: ${labels[item.zone]}`}>
              {index + 1}
            </button>)}
          </div>
          <div className="rotation-mobile" aria-label="Sector zones on mobile">
            {['IMPROVING', 'LEADING', 'LAGGING', 'WEAKENING'].map((state) => <section className={`rotation-mobile-zone rotation-zone--${state.toLowerCase()}`} key={state} aria-label={`${labels[state]} sectors`}>
              <h3>{labels[state]}</h3>
              {plotted.filter((item) => item.zone === state).map((item) => <button className="secondary-button" key={item.code} onClick={() => setSelected(item.code)} aria-pressed={selected === item.code} aria-label={`${item.name} in ${labels[state]}`}>
                {item.name}<small>{number(item.rs3m)}</small>
              </button>)}
            </section>)}
          </div>
          <div className="rotation-axis-title">3-month relative strength (pp) →</div>
          {!plotted.length && <p>No sectors have comparable history yet. Current RS is listed below.</p>}
          {chosen && <SectorStocks key={`${chosen.code}:${data.dataAsOf}`} sector={chosen} asOf={data.dataAsOf} onUnauthorized={onUnauthorized} onNavigate={onNavigate} />}
          <section className="sector-legend" aria-label="Sector relative strength ranking">
            <div className="sector-legend__head" aria-hidden="true"><span>Rank</span><span>Sector</span><span>Zone</span><span>3M RS</span><span>Momentum</span><span>Coverage</span></div>
            {items.map((item) => <button key={item.code} className="sector-choice" onClick={() => setSelected(item.code)} aria-pressed={selected === item.code} aria-label={`${item.name}. ${labels[item.zone] || item.zone}. Three month relative strength ${number(item.rs3m)}. Momentum ${number(item.momentum)}. One month ${number(item.rs1m)}, six month ${number(item.rs6m)}, twelve month ${number(item.rs12m)}. ${item.coveredCount} of ${item.memberCount} stocks covered.`}>
              <span>{plotted.indexOf(item) >= 0 ? plotted.indexOf(item) + 1 : '—'}</span><strong title={item.name}>{item.name}</strong><span>{labels[item.zone] || item.zone}</span><span>{number(item.rs3m)}</span><span>{number(item.momentum)}</span><span>{item.coveredCount}/{item.memberCount}{item.isPartial ? ' partial' : ''}</span>
            </button>)}
          </section>
        </>}
        <details><summary>How sector rotation is calculated</summary><p>{data.methodology}</p><p>Leading: positive RS, rising momentum. Weakening: positive RS, falling momentum. Lagging: negative RS, falling momentum. Improving: negative RS, rising momentum. Zero is included on the positive side. Rankings describe evidence, not buy recommendations or win probabilities.</p></details>
      </>}
    </ResourceState>
  </section>
}

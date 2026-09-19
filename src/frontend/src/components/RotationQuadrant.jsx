import { useState } from 'react'
import { formatNumber } from '../utils/formatters.js'

export const ROTATION_ZONE_LABELS = {
  LEADING: 'Leading', WEAKENING: 'Weakening', LAGGING: 'Lagging',
  IMPROVING: 'Improving', UNAVAILABLE: 'Insufficient history',
}

const TRAIL_COLORS = ['#ffdf84', '#8fd8ff', '#a8e6a2', '#ffad8c', '#d8b4fe', '#7ee7cf', '#f5b7db', '#c4df74']

function usableTrail(rotation) {
  const trail = (rotation?.trail || []).filter((point) => point.strength != null && point.momentum != null)
  return trail.length ? trail : rotation?.strength != null && rotation?.momentum != null
    ? [{ strength: rotation.strength, momentum: rotation.momentum }]
    : []
}

export default function RotationQuadrant({ title, description, items, itemId, itemLabel, onOpen, emptyMessage, ariaLabel, selectedId }) {
  const [highlightedId, setHighlightedId] = useState('')
  const plotted = items.filter((item) => item.rotation?.strength != null && item.rotation?.momentum != null)
  const positions = plotted.flatMap((item) => usableTrail(item.rotation))
  const xMax = Math.max(1, ...positions.map((point) => Math.abs(Number(point.strength)))) * 1.15
  const yMax = Math.max(1, ...positions.map((point) => Math.abs(Number(point.momentum)))) * 1.15
  const coordinates = (point) => ({ x: 50 + Number(point.strength) / xMax * 44, y: 50 - Number(point.momentum) / yMax * 44 })
  const emphasisClass = (id) => highlightedId && highlightedId !== id ? ' is-muted' : highlightedId === id ? ' is-highlighted' : ''

  return <section className="watchlist-quadrant" aria-labelledby="rotation-quadrant-title">
    <header><div><h2 id="rotation-quadrant-title">{title}</h2><p>{description}</p></div><span>{plotted.length}/{items.length} plotted</span></header>
    {plotted.length ? <>
      <div className="rotation-axis-title">↑ RS momentum proxy (pp): accelerating above zero</div>
      <div className="rotation-plot" role="group" aria-label={ariaLabel} onMouseLeave={() => setHighlightedId('')}>
        <div className="rotation-zone rotation-zone--improving">Improving</div><div className="rotation-zone rotation-zone--leading">Leading</div>
        <div className="rotation-zone rotation-zone--lagging">Lagging</div><div className="rotation-zone rotation-zone--weakening">Weakening</div><span className="rotation-origin">0</span>
        <svg className="watchlist-quadrant__trails" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">{plotted.map((item, index) => {
          const path = usableTrail(item.rotation).map((point) => coordinates(point))
          const id = itemId(item)
          return <polyline key={id} className={`watchlist-quadrant__trail${emphasisClass(id)}`} style={{ '--trail-color': TRAIL_COLORS[index % TRAIL_COLORS.length] }} fill="none" stroke="currentColor" strokeWidth="1.25" vectorEffect="non-scaling-stroke" points={path.map(({ x, y }) => `${x},${y}`).join(' ')} />
        })}</svg>
        {plotted.map((item, index) => { const id = itemId(item); const latest = coordinates(item.rotation); const sessions = usableTrail(item.rotation).length; const label = itemLabel(item); return <button key={id} className={`rotation-point watchlist-quadrant__point${selectedId === id ? ' is-selected' : ''}${emphasisClass(id)}`} style={{ left: `${latest.x}%`, top: `${latest.y}%` }} onMouseEnter={() => setHighlightedId(id)} onFocus={() => setHighlightedId(id)} onBlur={() => setHighlightedId('')} onClick={() => onOpen(item)} aria-pressed={selectedId === id || undefined} aria-label={`${label}: ${ROTATION_ZONE_LABELS[item.rotation.zone]}, 3-month RS ${formatNumber(item.rotation.strength)} percentage points, momentum ${formatNumber(item.rotation.momentum)} percentage points. Path shows ${sessions} recent trading sessions.`} title={`${label}: ${ROTATION_ZONE_LABELS[item.rotation.zone]} (${sessions}-session path)`}>{index + 1}</button> })}
      </div>
      <div className="rotation-mobile" aria-label={`${title} zones on mobile`}>{['IMPROVING', 'LEADING', 'LAGGING', 'WEAKENING'].map((zone) => <section className={`rotation-mobile-zone rotation-zone--${zone.toLowerCase()}`} key={zone}><h3>{ROTATION_ZONE_LABELS[zone]}</h3>{plotted.filter((item) => item.rotation.zone === zone).map((item) => <button className="secondary-button" key={itemId(item)} onClick={() => onOpen(item)}>{itemLabel(item)}<small>{formatNumber(item.rotation.strength)} pp RS</small></button>)}</section>)}</div>
      <div className="rotation-axis-title">3-month relative strength (pp) →</div>
      <div className="watchlist-quadrant__legend" role="list" aria-label={`${title} quadrant values`} onMouseLeave={() => setHighlightedId('')}>{plotted.map((item, index) => { const id = itemId(item); return <div role="listitem" key={id} className={emphasisClass(id)}><button onMouseEnter={() => setHighlightedId(id)} onFocus={() => setHighlightedId(id)} onBlur={() => setHighlightedId('')} onClick={() => onOpen(item)}><span className="watchlist-quadrant__key" style={{ '--trail-color': TRAIL_COLORS[index % TRAIL_COLORS.length] }}>{index + 1}</span><strong>{itemLabel(item)}</strong><span>{ROTATION_ZONE_LABELS[item.rotation.zone]}</span><span>{formatNumber(item.rotation.strength)} pp RS</span><span>{formatNumber(item.rotation.momentum)} pp momentum</span><small>{usableTrail(item.rotation).length}-session path</small></button></div> })}</div>
    </> : <p className="muted-copy">{emptyMessage}</p>}
    <details><summary>How the quadrant is calculated</summary><p>Each line connects up to five recent trading-session positions, oldest to newest; the numbered marker is the latest point. X is 3-month benchmark-relative return. Y is 1-month RS minus one-third of 3-month RS. Zero divides each axis. This is a momentum proxy and ranking aid, not a forecast or trade recommendation.</p></details>
  </section>
}

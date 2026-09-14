import { formatMarketDate, formatNumber, formatPercent } from '../utils/formatters.js'

const WIDTH = 520
const HEIGHT = 132
const PADDING = 8

function chartPoints(series) {
  const values = series.map((point) => Number(point.close)).filter(Number.isFinite)
  if (values.length < 2) return ''
  const minimum = Math.min(...values)
  const maximum = Math.max(...values)
  const range = maximum - minimum || 1
  return values.map((value, index) => {
    const x = PADDING + index * ((WIDTH - PADDING * 2) / (values.length - 1))
    const y = PADDING + (maximum - value) * ((HEIGHT - PADDING * 2) / range)
    return `${x.toFixed(2)},${y.toFixed(2)}`
  }).join(' ')
}

export default function MarketIndexChart({ index }) {
  const series = index?.series?.filter((point) => point.close != null) ?? []
  const points = chartPoints(series)
  const areaPoints = points ? `${PADDING},${HEIGHT - PADDING} ${points} ${WIDTH - PADDING},${HEIGHT - PADDING}` : ''

  return <section className="market-index" aria-labelledby={`market-index-${index?.code ?? 'unknown'}`}>
    <div className="market-index__header">
      <div><h3 id={`market-index-${index?.code ?? 'unknown'}`}>{index?.name ?? 'Index'}</h3><p>{formatMarketDate(index?.dataAsOf)}</p></div>
      <div className="market-index__value"><strong>{formatNumber(index?.lastClose)}</strong><span className={Number(index?.periodChangePct) >= 0 ? 'is-positive' : 'is-negative'}>{formatPercent(index?.periodChangePct, { signed: true })} over 3 months</span></div>
    </div>
    {points ? <>
      <svg className="market-index__chart" viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img" aria-label={`${index.name} closing prices over the latest 63 trading sessions`}>
        <line x1={PADDING} y1={HEIGHT / 2} x2={WIDTH - PADDING} y2={HEIGHT / 2} className="market-index__guide" />
        <polygon points={areaPoints} className="market-index__area" />
        <polyline points={points} className="market-index__line" />
      </svg>
      <details className="market-index__data"><summary>View index values</summary><div className="market-index__table-wrap"><table><caption>{index.name} closing-price history</caption><thead><tr><th>Date</th><th>Close</th></tr></thead><tbody>{series.map((point) => <tr key={point.date}><td>{formatMarketDate(point.date)}</td><td>{formatNumber(point.close)}</td></tr>)}</tbody></table></div></details>
    </> : <p className="market-index__empty">Index history is not available yet.</p>}
  </section>
}

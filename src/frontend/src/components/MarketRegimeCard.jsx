import { formatPercent } from '../utils/formatters.js'
import MarketIndexChart from './MarketIndexChart.jsx'

export default function MarketRegimeCard({ market }) {
  const nifty50 = market.indices?.find((index) => index.code === 'NIFTY 50')
  return <article className="regime-card">
    <header className="regime-card__header"><p className="eyebrow">Market regime</p><strong className="regime-badge">{market.label}</strong></header>
    <MarketIndexChart index={nifty50 ?? { code: 'NIFTY 50', name: 'NIFTY 50', series: [] }} />
    <div className="regime-card__benchmark">
      <div className="regime-card__benchmark-heading"><h3>NIFTY 500</h3><span>Breadth</span></div>
      <dl className="market-breadth"><div><dt>Above EMA20</dt><dd>{formatPercent(market.aboveEma20Pct)}</dd></div><div><dt>Above SMA50</dt><dd>{formatPercent(market.aboveSma50Pct)}</dd></div><div><dt>Above SMA200</dt><dd>{formatPercent(market.aboveSma200Pct)}</dd></div><div><dt>52-week highs</dt><dd>{market.new52WeekHighs ?? '—'}</dd></div><div><dt>Breakouts</dt><dd>{market.breakouts ?? '—'}</dd></div><div><dt>Failed breakouts</dt><dd>{market.failedBreakouts ?? '—'}</dd></div></dl>
    </div>
  </article>
}

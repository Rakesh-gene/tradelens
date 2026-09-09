import { formatPercent, formatScore } from '../utils/formatters.js'

export default function MarketRegimeCard({ market }) {
  return <article className="regime-card"><p className="eyebrow">Market regime</p><div className="regime-score">{formatScore(market.regimeScore)}</div><h2>{market.label}</h2><p>{market.benchmark}</p><dl><div><dt>Above EMA20</dt><dd>{formatPercent(market.aboveEma20Pct)}</dd></div><div><dt>Above SMA50</dt><dd>{formatPercent(market.aboveSma50Pct)}</dd></div><div><dt>Above SMA200</dt><dd>{formatPercent(market.aboveSma200Pct)}</dd></div><div><dt>52-week highs</dt><dd>{market.new52WeekHighs ?? '—'}</dd></div><div><dt>Breakouts</dt><dd>{market.breakouts ?? '—'}</dd></div><div><dt>Failed breakouts</dt><dd>{market.failedBreakouts ?? '—'}</dd></div></dl></article>
}

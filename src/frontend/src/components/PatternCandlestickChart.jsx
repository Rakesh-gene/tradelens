import React, { useEffect, useMemo, useRef } from 'react'
import { formatCompactNumber, formatMarketDate, formatPrice } from '../utils/formatters.js'
import { CandlestickSeries, HistogramSeries, LineSeries, LineStyle, createChart, createSeriesMarkers } from 'lightweight-charts'

const number = (value) => Number.isFinite(Number(value)) ? Number(value) : null
const triggeredState = (state) => ['TRIGGERED', 'CONFIRMED'].includes(state)

export default function PatternCandlestickChart({ candles = [], levels = {}, evidence = [], corporateActions = [], patternWindow, range, onRangeChange }) {
  const container = useRef(null)
  const rows = useMemo(() => candles.map((item) => ({ time: item.date, open: number(item.open), high: number(item.high), low: number(item.low), close: number(item.close), volume: number(item.volume), ema20: number(item.ema20), sma50: number(item.sma50), sma200: number(item.sma200) })).filter((item) => item.time && [item.open, item.high, item.low, item.close].every((value) => value != null)), [candles])

  useEffect(() => {
    if (!container.current || !rows.length) return undefined
    const chart = createChart(container.current, {
      width: container.current.clientWidth,
      height: 410,
      layout: { background: { color: '#0b0e12' }, textColor: 'rgba(246, 236, 214, 0.7)', fontFamily: 'Avenir Next, Segoe UI, sans-serif' },
      grid: { vertLines: { color: 'rgba(255, 236, 199, 0.06)' }, horzLines: { color: 'rgba(255, 236, 199, 0.10)' } },
      rightPriceScale: { borderColor: 'rgba(255, 236, 199, 0.12)', entireTextOnly: true },
      timeScale: { borderColor: 'rgba(255, 236, 199, 0.12)', timeVisible: false, secondsVisible: false },
      crosshair: { vertLine: { color: 'rgba(255, 223, 132, 0.42)' }, horzLine: { color: 'rgba(255, 223, 132, 0.42)' } },
      handleScroll: true,
      handleScale: true,
    })
    const series = chart.addSeries(CandlestickSeries, {
      upColor: '#78c579', downColor: '#db5e5e', borderVisible: false,
      wickUpColor: '#78c579', wickDownColor: '#db5e5e',
      priceFormat: { type: 'price', precision: 2, minMove: 0.01 },
    })
    series.setData(rows)
    const averages = [['ema20', 'EMA 20', '#ffdf84'], ['sma50', 'SMA 50', '#78c579'], ['sma200', 'SMA 200', '#f28d3f']]
    averages.forEach(([key, title, color]) => {
      const values = rows.filter((row) => row[key] != null).map((row) => ({ time: row.time, value: row[key] }))
      if (values.length) { const average = chart.addSeries(LineSeries, { title, color, lineWidth: 1, priceLineVisible: false, lastValueVisible: false }); average.setData(values) }
    })
    const volumeValues = rows.filter((row) => row.volume != null).map((row) => ({ time: row.time, value: row.volume, color: row.close >= row.open ? 'rgba(120, 197, 121, 0.32)' : 'rgba(219, 94, 94, 0.32)' }))
    if (volumeValues.length) { const volume = chart.addSeries(HistogramSeries, { priceFormat: { type: 'volume' }, priceScaleId: '' }); volume.priceScale().applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } }); volume.setData(volumeValues) }
    const lineDetails = [
      ['pivot', 'Trigger', '#ffdf84'], ['support', 'Support', '#c6f7c8'], ['invalidation', 'Invalidation', '#ffd1d1'],
    ]
    lineDetails.forEach(([key, title, color]) => {
      const price = number(levels[key])
      if (price != null) series.createPriceLine({ price, title, color, lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: true })
    })
    const visibleTimes = new Set(rows.map((row) => row.time))
    const patternMarkers = evidence.map((item) => {
      const triggered = triggeredState(item.state)
      const time = triggered ? item.triggerDate : item.detectedDate
      if (!time || !visibleTimes.has(time)) return null
      return { time, position: triggered ? 'aboveBar' : 'belowBar', color: triggered ? '#ffdf84' : 'rgba(198, 247, 200, 0.82)', shape: triggered ? 'arrowUp' : 'circle', text: `${item.variant || item.patternType} · ${item.state}` }
    }).filter(Boolean)
    const actionMarkers = corporateActions.filter((item) => item.exDate && visibleTimes.has(item.exDate)).map((item) => ({ time: item.exDate, position: 'belowBar', color: '#f28d3f', shape: 'square', text: item.actionType }))
    const windowMarkers = [{ time: patternWindow?.startDate, text: 'Pattern window starts' }, { time: patternWindow?.endDate, text: 'Pattern window updated' }].filter((item) => item.time && visibleTimes.has(item.time)).map((item) => ({ ...item, position: 'belowBar', color: 'rgba(255, 223, 132, 0.72)', shape: 'circle' }))
    const markers = [...patternMarkers, ...actionMarkers, ...windowMarkers].sort((left, right) => left.time.localeCompare(right.time))
    if (markers.length) createSeriesMarkers(series, markers)
    chart.timeScale().fitContent()
    const observer = new ResizeObserver(([entry]) => chart.applyOptions({ width: entry.contentRect.width }))
    observer.observe(container.current)
    return () => { observer.disconnect(); chart.remove() }
  }, [corporateActions, evidence, levels, patternWindow, rows])

  if (!rows.length) return <p className="muted-copy">No adjusted daily prices are available for this pattern version yet.</p>
  const triggered = evidence.filter((item) => triggeredState(item.state)).length
  return <figure className="price-chart" aria-labelledby="price-chart-title"><figcaption><div><p className="eyebrow">Adjusted price action</p><h2 id="price-chart-title">Candlestick chart</h2><p>Use the crosshair for exact OHLC values. Detected, forming, ready, triggered and confirmed evidence is marked using its effective date.</p></div><div className="price-chart__controls"><label>Chart range<select className="select-control" value={range} onChange={(event) => onRangeChange(event.target.value)}><option value="3m">3 months</option><option value="6m">6 months</option><option value="1y">1 year</option><option value="5y">5 years</option><option value="10y">10 years</option></select></label><div className="price-chart__legend" aria-label="Chart legend"><span className="is-up">Up day</span><span className="is-down">Down day</span><span className="is-level">Trade levels</span><span className="is-signal">{triggered} triggered signal{triggered === 1 ? '' : 's'}</span><span>EMA20 · SMA50 · SMA200 · Volume</span></div></div></figcaption><div ref={container} className="price-chart__canvas" aria-label="Interactive candlestick price chart" />{corporateActions.length > 0 && <details><summary>{corporateActions.length} corporate action{corporateActions.length === 1 ? '' : 's'} in range</summary><ul>{corporateActions.map((action) => <li key={action.sourceEventKey}>{formatMarketDate(action.exDate)} · {action.actionType}{action.description ? ` · ${action.description}` : ''}</li>)}</ul></details>}<details className="chart-data-table"><summary>Open accessible price summary</summary><div className="setup-table-wrap"><table><caption>Latest 20 adjusted daily bars in the selected range</caption><thead><tr><th scope="col">Date</th><th scope="col">Open</th><th scope="col">High</th><th scope="col">Low</th><th scope="col">Close</th><th scope="col">Volume</th><th scope="col">EMA20</th><th scope="col">SMA50</th><th scope="col">SMA200</th></tr></thead><tbody>{candles.slice(-20).reverse().map((bar) => <tr key={bar.date}><th scope="row">{formatMarketDate(bar.date)}</th><td>{formatPrice(bar.open)}</td><td>{formatPrice(bar.high)}</td><td>{formatPrice(bar.low)}</td><td>{formatPrice(bar.close)}</td><td>{formatCompactNumber(bar.volume)}</td><td>{formatPrice(bar.ema20)}</td><td>{formatPrice(bar.sma50)}</td><td>{formatPrice(bar.sma200)}</td></tr>)}</tbody></table></div></details></figure>
}

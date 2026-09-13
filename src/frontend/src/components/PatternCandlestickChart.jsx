import React, { useEffect, useMemo, useRef } from 'react'
import { formatCompactNumber, formatMarketDate, formatPrice } from '../utils/formatters.js'
import { CandlestickSeries, HistogramSeries, LineSeries, LineStyle, createChart, createSeriesMarkers } from 'lightweight-charts'
import { groupPatternDetections, patternChartGeometry } from '../utils/patternChartOverlays.js'

const number = (value) => Number.isFinite(Number(value)) ? Number(value) : null

export default function PatternCandlestickChart({
  candles = [], levels = {}, evidence = [], corporateActions = [],
  selectedPatternId, range, onRangeChange,
}) {
  const container = useRef(null)
  const rows = useMemo(() => candles.map((item) => ({
    time: item.date, open: number(item.open), high: number(item.high), low: number(item.low),
    close: number(item.close), volume: number(item.volume), ema20: number(item.ema20),
    sma50: number(item.sma50), sma200: number(item.sma200),
  })).filter((item) => item.time && [item.open, item.high, item.low, item.close].every((value) => value != null)), [candles])
  const selectedPattern = useMemo(
    () => selectedPatternId ? evidence.find((item) => item.patternInstanceId === selectedPatternId) : null,
    [evidence, selectedPatternId],
  )
  const detectionGroups = useMemo(() => groupPatternDetections(evidence, rows), [evidence, rows])

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
      if (values.length) {
        const average = chart.addSeries(LineSeries, { title, color, lineWidth: 1, priceLineVisible: false, lastValueVisible: false })
        average.setData(values)
      }
    })
    const volumeValues = rows.filter((row) => row.volume != null).map((row) => ({
      time: row.time, value: row.volume,
      color: row.close >= row.open ? 'rgba(120, 197, 121, 0.32)' : 'rgba(219, 94, 94, 0.32)',
    }))
    if (volumeValues.length) {
      const volume = chart.addSeries(HistogramSeries, { priceFormat: { type: 'volume' }, priceScaleId: '' })
      volume.priceScale().applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } })
      volume.setData(volumeValues)
    }

    ;[['pivot', 'Trigger', '#ffdf84'], ['support', 'Support', '#c6f7c8'], ['invalidation', 'Invalidation', '#ffd1d1']].forEach(([key, title, color]) => {
      const price = number(levels[key])
      if (price != null) series.createPriceLine({ price, title, color, lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: true })
    })

    const visibleTimes = new Set(rows.map((row) => row.time))
    const patternMarkers = detectionGroups.map(({ time, patterns }) => {
      const includesSelected = patterns.some((item) => item.patternInstanceId === selectedPatternId)
      const names = patterns.map((item) => item.variant || item.patternType)
      const text = names.length === 1 ? names[0] : names.length === 2 ? names.join(' + ') : `${names.length} patterns`
      return {
        time, position: 'aboveBar', color: includesSelected ? '#77d9d0' : '#ffdf84',
        shape: includesSelected ? 'arrowDown' : 'circle', text,
      }
    })
    const actionMarkers = corporateActions
      .filter((item) => item.exDate && visibleTimes.has(item.exDate))
      .map((item) => ({ time: item.exDate, position: 'belowBar', color: '#f28d3f', shape: 'square', text: item.actionType }))
    const markers = [...patternMarkers, ...actionMarkers].sort((left, right) => left.time.localeCompare(right.time))
    if (markers.length) createSeriesMarkers(series, markers)

    const geometry = patternChartGeometry(selectedPattern, rows)
    if (geometry) {
      const overlay = chart.addSeries(LineSeries, {
        title: geometry.title, color: '#77d9d0', lineWidth: 3,
        priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: true,
      })
      overlay.setData(geometry.points.map(({ time, value }) => ({ time, value })))
      createSeriesMarkers(overlay, geometry.points.map(({ time, label }, index) => ({
        time, position: index % 2 ? 'belowBar' : 'aboveBar',
        color: '#77d9d0', shape: 'circle', text: label,
      })))
    }

    chart.timeScale().fitContent()
    const observer = new ResizeObserver(([entry]) => chart.applyOptions({ width: entry.contentRect.width }))
    observer.observe(container.current)
    return () => { observer.disconnect(); chart.remove() }
  }, [corporateActions, detectionGroups, levels, rows, selectedPattern, selectedPatternId])

  if (!rows.length) return <p className="muted-copy">No adjusted daily prices are available for this pattern version yet.</p>
  const displayedCount = detectionGroups.reduce((count, group) => count + group.patterns.length, 0)
  return <figure className="price-chart" aria-labelledby="price-chart-title">
    <figcaption>
      <div><p className="eyebrow">Adjusted price action</p><h2 id="price-chart-title">Candlestick chart</h2><p>Every pattern found within this chart range is marked on its detection date. The selected pattern is highlighted in teal.</p></div>
      <div className="price-chart__controls">
        <label>Chart range<select className="select-control" value={range} onChange={(event) => onRangeChange(event.target.value)}><option value="3m">3 months</option><option value="6m">6 months</option><option value="1y">1 year</option><option value="5y">5 years</option><option value="10y">10 years</option></select></label>
        <div className="price-chart__legend" aria-label="Chart legend"><span className="is-up">Up day</span><span className="is-down">Down day</span><span className="is-level">Trade levels</span>{selectedPattern && <span className="is-pattern">Selected pattern</span>}<span className="is-signal">{displayedCount} pattern{displayedCount === 1 ? '' : 's'} in range</span><span>EMA20 · SMA50 · SMA200 · Volume</span></div>
      </div>
    </figcaption>
    <div ref={container} className="price-chart__canvas" aria-label="Interactive candlestick price chart" />
    {displayedCount > 0 && <details className="chart-pattern-index"><summary>{displayedCount} detected pattern{displayedCount === 1 ? '' : 's'} shown on the chart</summary><ol>{detectionGroups.map(({ time, patterns }) => <li key={time}><time dateTime={time}>{formatMarketDate(time)}</time><span>{patterns.map((item) => `${item.variant || item.patternType} · ${item.state}`).join(', ')}</span></li>)}</ol></details>}
    {corporateActions.length > 0 && <details><summary>{corporateActions.length} corporate action{corporateActions.length === 1 ? '' : 's'} in range</summary><ul>{corporateActions.map((action) => <li key={action.sourceEventKey}>{formatMarketDate(action.exDate)} · {action.actionType}{action.description ? ` · ${action.description}` : ''}</li>)}</ul></details>}
    <details className="chart-data-table"><summary>Open accessible price summary</summary><div className="setup-table-wrap"><table><caption>Latest 20 adjusted daily bars in the selected range</caption><thead><tr><th scope="col">Date</th><th scope="col">Open</th><th scope="col">High</th><th scope="col">Low</th><th scope="col">Close</th><th scope="col">Volume</th><th scope="col">EMA20</th><th scope="col">SMA50</th><th scope="col">SMA200</th></tr></thead><tbody>{candles.slice(-20).reverse().map((bar) => <tr key={bar.date}><th scope="row">{formatMarketDate(bar.date)}</th><td>{formatPrice(bar.open)}</td><td>{formatPrice(bar.high)}</td><td>{formatPrice(bar.low)}</td><td>{formatPrice(bar.close)}</td><td>{formatCompactNumber(bar.volume)}</td><td>{formatPrice(bar.ema20)}</td><td>{formatPrice(bar.sma50)}</td><td>{formatPrice(bar.sma200)}</td></tr>)}</tbody></table></div></details>
  </figure>
}

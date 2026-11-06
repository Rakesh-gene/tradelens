import React, { useEffect, useMemo, useRef } from 'react'
import { formatMarketDate } from '../utils/formatters.js'
import { CandlestickSeries, HistogramSeries, LineSeries, LineStyle, createChart, createSeriesMarkers } from 'lightweight-charts'
import PatternShapePrimitive from '../utils/patternShapePrimitive.js'

const number = (value) => value == null || value === '' ? null : Number.isFinite(Number(value)) ? Number(value) : null

export default function PatternCandlestickChart({
  candles = [], levels = {}, evidence = [], corporateActions = [],
  milestones = [], patternAnnotations = [], selectedPatternId, range, onRangeChange,
}) {
  const container = useRef(null)
  const rows = useMemo(() => candles.map((item) => ({
    time: item.date, open: number(item.open), high: number(item.high), low: number(item.low),
    close: number(item.close), volume: number(item.volume), ema20: number(item.ema20),
    sma50: number(item.sma50), sma200: number(item.sma200),
  })).filter((item) => item.time && [item.open, item.high, item.low, item.close].every((value) => value != null)), [candles])
  const focusedPattern = useMemo(
    () => selectedPatternId ? patternAnnotations.find((item) => item.patternInstanceId === selectedPatternId) : patternAnnotations.filter((item) => item.confirmationDate).at(-1),
    [patternAnnotations, selectedPatternId],
  )
  const confirmations = useMemo(() => {
    const dates = new Set(rows.map((row) => row.time))
    return patternAnnotations.filter((item) => item.confirmationDate && dates.has(item.confirmationDate))
  }, [patternAnnotations, rows])

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

    ;[['pivot', 'Trigger', '#ffdf84'], ['support', 'Support', '#c6f7c8'], ['invalidation', 'Invalidation', '#ffd1d1'], ['entry', 'Entry', '#77d9d0'], ['stop', 'Stop', '#ffd1d1'], ['target', 'Target', '#ffdf84'], ['exit', 'Exit', '#f28d3f']].forEach(([key, title, color]) => {
      const price = number(levels[key])
      if (price != null) series.createPriceLine({ price, title, color, lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: true })
    })

    const visibleTimes = new Set(rows.map((row) => row.time))
    const byDate = new Map()
    confirmations.filter((item) => !selectedPatternId || item.patternInstanceId === selectedPatternId).forEach((item) => {
      const group = byDate.get(item.confirmationDate) || []
      group.push(item); byDate.set(item.confirmationDate, group)
    })
    const patternMarkers = [...byDate].map(([time, items]) => ({
      time, position: items.every((item) => item.direction === 'BEARISH') ? 'aboveBar' : 'belowBar', color: '#77d9d0',
      shape: items.every((item) => item.direction === 'BEARISH') ? 'arrowDown' : 'arrowUp',
      text: `Entry confirmed · ${items.length > 1 ? `${items.length} setups` : items[0].variant || items[0].patternType}`,
    }))
    const actionMarkers = corporateActions
      .filter((item) => item.exDate && visibleTimes.has(item.exDate))
      .map((item) => ({ time: item.exDate, position: 'belowBar', color: '#f28d3f', shape: 'square', text: item.actionType }))
    const milestoneMarkers = milestones.filter((item) => item.date && visibleTimes.has(item.date)).map((item) => ({ time: item.date, position: 'belowBar', color: '#77d9d0', shape: 'arrowUp', text: `${item.label} ${item.returnPct == null ? 'pending' : `${Number(item.returnPct) >= 0 ? '+' : ''}${Number(item.returnPct).toFixed(1)}%`}` }))
    const markers = [...patternMarkers, ...actionMarkers, ...milestoneMarkers].sort((left, right) => left.time.localeCompare(right.time))
    if (markers.length) createSeriesMarkers(series, markers)

    if (focusedPattern?.shapes?.length) series.attachPrimitive(new PatternShapePrimitive(focusedPattern.shapes))

    chart.timeScale().fitContent()
    const observer = new ResizeObserver(([entry]) => chart.applyOptions({ width: entry.contentRect.width }))
    observer.observe(container.current)
    return () => { observer.disconnect(); chart.remove() }
  }, [corporateActions, confirmations, levels, milestones, rows, focusedPattern, selectedPatternId])

  if (!rows.length) return <p className="muted-copy">No adjusted daily prices are available for this pattern version yet.</p>
  const visibleConfirmations = confirmations.filter((item) => !selectedPatternId || item.patternInstanceId === selectedPatternId)
  const chartDescription = focusedPattern
    ? `${focusedPattern.variant || focusedPattern.patternType}, recorded state ${focusedPattern.state}. ${focusedPattern.confirmationDate ? `Entry confirmed ${formatMarketDate(focusedPattern.confirmationDate)}.` : 'No recorded entry confirmation in this chart range.'} ${focusedPattern.shapes?.length ? 'Pattern structure shown.' : 'Stored pattern geometry is unavailable in this chart range.'}`
    : 'Interactive adjusted candlestick price chart.'
  return <figure className="price-chart" aria-labelledby="price-chart-title">
    <figcaption>
      <div><h2 id="price-chart-title">Candlestick chart</h2></div>
      <div className="price-chart__controls">
        {onRangeChange && <label>Chart range<select className="select-control" value={range} onChange={(event) => onRangeChange(event.target.value)}><option value="3m">3 months</option><option value="6m">6 months</option><option value="1y">1 year</option><option value="5y">5 years</option><option value="10y">10 years</option></select></label>}
        <div className="price-chart__legend" aria-label="Chart legend"><span className="is-up">Up day</span><span className="is-down">Down day</span><span className="is-level">Reference levels</span>{focusedPattern?.shapes?.length > 0 && <span className="is-pattern">Pattern structure</span>}{milestones.length > 0 && <span>3M · 6M · 1Y observations</span>}<span className="is-signal">{visibleConfirmations.length} entry confirmation{visibleConfirmations.length === 1 ? '' : 's'}</span><span>EMA20 · SMA50 · SMA200 · Volume</span></div>
      </div>
    </figcaption>
    <div ref={container} className="price-chart__canvas" role="img" aria-label={chartDescription} />
  </figure>
}

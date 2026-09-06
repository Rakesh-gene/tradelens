import React, { useEffect, useRef } from 'react'
import { CandlestickSeries, LineStyle, createChart, createSeriesMarkers } from 'lightweight-charts'

const number = (value) => Number.isFinite(Number(value)) ? Number(value) : null
const triggeredState = (state) => ['TRIGGERED', 'CONFIRMED'].includes(state)

export default function PatternCandlestickChart({ candles = [], levels = {}, evidence = [], range, onRangeChange }) {
  const container = useRef(null)
  const rows = candles.map((item) => ({ time: item.date, open: number(item.open), high: number(item.high), low: number(item.low), close: number(item.close) })).filter((item) => item.time && [item.open, item.high, item.low, item.close].every((value) => value != null))

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
    const lineDetails = [
      ['pivot', 'Trigger', '#ffdf84'], ['support', 'Support', '#c6f7c8'], ['invalidation', 'Invalidation', '#ffd1d1'],
    ]
    lineDetails.forEach(([key, title, color]) => {
      const price = number(levels[key])
      if (price != null) series.createPriceLine({ price, title, color, lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: true })
    })
    const visibleTimes = new Set(rows.map((row) => row.time))
    const markers = evidence.filter((item) => triggeredState(item.state) && item.triggerDate && visibleTimes.has(item.triggerDate)).map((item) => ({
      time: item.triggerDate, position: 'aboveBar', color: '#ffdf84', shape: 'arrowUp', text: `${item.variant || item.patternType} triggered`,
    }))
    if (markers.length) createSeriesMarkers(series, markers)
    chart.timeScale().fitContent()
    const observer = new ResizeObserver(([entry]) => chart.applyOptions({ width: entry.contentRect.width }))
    observer.observe(container.current)
    return () => { observer.disconnect(); chart.remove() }
  }, [candles, evidence, levels, rows])

  if (!rows.length) return <p className="muted-copy">No adjusted daily prices are available for this pattern version yet.</p>
  const triggered = evidence.filter((item) => triggeredState(item.state)).length
  return <figure className="price-chart" aria-labelledby="price-chart-title"><figcaption><div><p className="eyebrow">Price action</p><h2 id="price-chart-title">Candlestick chart</h2><p>Use the crosshair for exact OHLC values. Only confirmed or triggered signals are marked on the chart.</p></div><div className="price-chart__controls"><label>Chart range<select value={range} onChange={(event) => onRangeChange(event.target.value)}><option value="3m">3 months</option><option value="6m">6 months</option><option value="1y">1 year</option><option value="5y">5 years</option><option value="max">Max</option></select></label><div className="price-chart__legend" aria-label="Chart legend"><span className="is-up">Up day</span><span className="is-down">Down day</span><span className="is-level">Trade levels</span><span className="is-signal">{triggered} triggered signal{triggered === 1 ? '' : 's'}</span></div></div></figcaption><div ref={container} className="price-chart__canvas" aria-label="Interactive candlestick price chart" /></figure>
}

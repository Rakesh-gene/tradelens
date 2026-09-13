function candlePrice(candlesByDate, patternDate, priceKey) {
  const candle = candlesByDate.get(patternDate)
  const value = candle?.[priceKey]
  return Number.isFinite(value) ? value : null
}

function point(candlesByDate, patternDate, priceKey, label) {
  const value = candlePrice(candlesByDate, patternDate, priceKey)
  return patternDate && value != null ? { time: patternDate, value, label } : null
}

export function patternChartGeometry(pattern, rows) {
  if (!pattern) return null
  const measurements = pattern.measurements || {}
  const candlesByDate = new Map(rows.map((row) => [row.time, row]))
  let points = []
  let title = pattern.variant || pattern.patternType || 'Selected pattern'

  if (pattern.patternType === 'REV-DBOT' || pattern.patternType === 'REV-DTOP') {
    const outerPrice = pattern.patternType === 'REV-DBOT' ? 'low' : 'high'
    const necklinePrice = pattern.patternType === 'REV-DBOT' ? 'high' : 'low'
    points = [
      point(candlesByDate, measurements.first_pivot_date, outerPrice, pattern.patternType === 'REV-DBOT' ? 'Bottom 1' : 'Top 1'),
      point(candlesByDate, measurements.neckline_pivot_date, necklinePrice, 'Neckline'),
      point(candlesByDate, measurements.second_pivot_date, outerPrice, pattern.patternType === 'REV-DBOT' ? 'Bottom 2' : 'Top 2'),
    ]
  } else if (pattern.patternType === 'HARM-ABCD') {
    const bullish = pattern.direction === 'BULLISH'
    const priceKeys = bullish ? ['high', 'low', 'high', 'low'] : ['low', 'high', 'low', 'high']
    points = ['a', 'b', 'c', 'd'].map((name, index) =>
      point(candlesByDate, measurements[`${name}_date`], priceKeys[index], name.toUpperCase()),
    )
  }

  const visiblePoints = points.filter(Boolean)
  return visiblePoints.length >= 2 ? { title, points: visiblePoints } : null
}

export function groupPatternDetections(evidence, rows) {
  const visibleDates = new Set(rows.map((row) => row.time))
  const grouped = new Map()
  evidence.forEach((pattern) => {
    if (!pattern.detectedDate || !visibleDates.has(pattern.detectedDate)) return
    const values = grouped.get(pattern.detectedDate) || []
    values.push(pattern)
    grouped.set(pattern.detectedDate, values)
  })
  return [...grouped.entries()]
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([time, patterns]) => ({ time, patterns }))
}


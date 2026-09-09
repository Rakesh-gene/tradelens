export const SETUP_STATES = ['DETECTED', 'FORMING', 'MATURE', 'READY', 'TRIGGERED', 'CONFIRMED', 'FAILED', 'INVALIDATED', 'EXPIRED']
export const PATTERN_CLASSES = ['BASE', 'BREAKOUT', 'PULLBACK', 'TREND', 'COMPRESSION', 'MOMENTUM', 'FAILURE']
export const SUPPORTED_PATTERN_TYPES = [
  'BASE-VCP', 'BASE-FLAT', 'BASE-52WH', 'BASE-TIGHT',
  'BRK-RANGE', 'BRK-52WH', 'BRK-ATH', 'BRK-MULTIY',
  'PB-BRKRET', 'PB-EMA20', 'PB-SMA50',
  'TREND-HHHL', 'TREND-S2', 'TREND-MA',
  'COMP-NR7', 'COMP-IB', 'COMP-ATR', 'COMP-RANGE',
  'MOM-ACC', 'MOM-RSL', 'MOM-RSB', 'VOL-DRY', 'VOL-EXP',
  'FAIL-BRK', 'FAIL-BASE', 'FAIL-EMA20', 'FAIL-SMA50', 'FAIL-STRUCT',
]
export const SETUP_SORTS = ['bestFit', 'setupScore', 'qualityScore', 'maturityScore', 'detectedDate', 'distanceToPivotPct']
export const EMPTY_SETUP_FILTERS = { asOf: '', state: '', patternClass: '', patternType: '', minSetupScore: '', sort: 'setupScore', direction: 'desc' }

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/

export function parseSetupFilters(search) {
  const query = new URLSearchParams(search)
  const filters = { ...EMPTY_SETUP_FILTERS }
  const corrected = []
  const enumValues = { state: SETUP_STATES, patternClass: PATTERN_CLASSES, sort: SETUP_SORTS, direction: ['asc', 'desc'] }
  for (const [name, allowed] of Object.entries(enumValues)) {
    const value = query.get(name)
    if (value && allowed.includes(value)) filters[name] = value
    else if (value) corrected.push(name)
  }
  filters.patternType = query.get('patternType')?.trim() || ''
  const asOf = query.get('asOf')
  if (asOf && ISO_DATE.test(asOf) && !Number.isNaN(Date.parse(`${asOf}T00:00:00Z`))) filters.asOf = asOf
  else if (asOf) corrected.push('asOf')
  for (const name of ['minSetupScore']) {
    const raw = query.get(name)
    if (!raw) continue
    const value = Number(raw)
    if (Number.isFinite(value) && value >= 0 && value <= 100) filters[name] = raw
    else corrected.push(name)
  }
  return { filters, cursor: query.get('cursor') || '', corrected }
}

export function setupQuery(filters, cursor = '') {
  return {
    pageSize: 25,
    asOf: filters.asOf,
    state: filters.state,
    patternClass: filters.patternClass,
    patternType: filters.patternType,
    minSetupScore: filters.minSetupScore,
    sort: filters.sort,
    direction: filters.direction,
    cursor,
  }
}

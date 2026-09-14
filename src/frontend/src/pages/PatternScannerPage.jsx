import React, { useMemo, useState } from 'react'
import { getPatterns } from '../api/marketApi.js'
import useApiResource from '../useApiResource.js'
import useDocumentTitle from '../hooks/useDocumentTitle.js'
import { PageIntro, SetupCard } from '../components/PatternUi.jsx'
import { EmptyState, ResourceState } from '../components/ResourceStates.jsx'
import { labelize } from '../utils/formatters.js'

const TIMEFRAMES = [
  { value: '1D', label: 'Daily', detail: 'End-of-day structures' },
  { value: '1W', label: 'Weekly', detail: 'Completed trading weeks' },
  { value: '1M', label: 'Monthly', detail: 'Completed trading months' },
]
const GROUPS = [
  { value: '', label: 'All pattern families' },
  { value: 'SETUP', label: 'Setups and supporting signals' },
  { value: 'REVERSAL', label: 'Reversals' },
  { value: 'CONTINUATION', label: 'Continuation' },
  { value: 'HARMONIC', label: 'Harmonic' },
]
const LIBRARY = [
  ['Bases and breakouts', 'Daily', ['VCP', 'Flat base', '52-week high base', 'Range breakout', 'Breakout retest']],
  ['Reversal', 'Double top/bottom live', ['Double bottom', 'Double top', 'Head and shoulders', 'Inverse head and shoulders', 'Rounding bottom']],
  ['Harmonic', 'AB=CD live', ['AB=CD', 'Gartley', 'Bat', 'Butterfly', 'Crab']],
  ['Continuation', 'Planned', ['Bull flag', 'Bear flag', 'Pennant', 'Wedge', 'Channel']],
]
const PATTERN_TYPE_LABELS = {
  'REV-DBOT': 'Double bottom',
  'REV-DTOP': 'Double top',
  'REV-IHS': 'Inverse head and shoulders',
  'REV-HS': 'Head and shoulders',
  'REV-CUP': 'Rounding bottom / cup',
  'CONT-FLAG-BULL': 'Bull flag',
  'CONT-FLAG-BEAR': 'Bear flag',
  'CONT-TRI-ASC': 'Ascending triangle',
  'CONT-TRI-DESC': 'Descending triangle',
  'CONT-TRI-SYM': 'Symmetrical triangle',
  'CONT-WEDGE-FALL': 'Falling wedge',
  'CONT-WEDGE-RISE': 'Rising wedge',
  'CONT-RECT': 'Rectangle',
  'HARM-ABCD': 'AB=CD',
  'HARM-GARTLEY': 'Gartley',
  'HARM-BAT': 'Bat',
  'HARM-BUTTERFLY': 'Butterfly',
  'HARM-CRAB': 'Crab',
  'HARM-CYPHER': 'Cypher',
  'HARM-SHARK': 'Shark',
  'HARM-5O': '5-0',
  'BASE-VCP': 'Volatility contraction pattern',
  'BASE-FLAT': 'Flat base',
  'BASE-52WH': '52-week-high base',
  'BASE-TIGHT': 'Tight base',
  'BRK-RANGE': 'Range breakout',
  'BRK-52WH': '52-week-high breakout',
  'BRK-ATH': 'All-time-high breakout',
  'BRK-MULTIY': 'Multi-year breakout',
  'PB-BRKRET': 'Breakout retest',
  'PB-EMA20': 'EMA 20 pullback',
  'PB-SMA50': 'SMA 50 pullback',
  'TREND-HHHL': 'Higher highs and higher lows',
  'TREND-S2': 'Stage 2 trend',
  'TREND-MA': 'Moving-average trend',
  'COMP-NR7': 'Narrowest range in 7 sessions',
  'COMP-IB': 'Inside bar',
  'COMP-ATR': 'ATR compression',
  'COMP-RANGE': 'Range compression',
  'MOM-ACC': 'Momentum acceleration',
  'MOM-RSL': 'Relative-strength leadership',
  'MOM-RSB': 'Relative-strength breakout',
  'VOL-DRY': 'Volume dry-up',
  'VOL-EXP': 'Volume expansion',
  'FAIL-BRK': 'Failed breakout',
  'FAIL-BASE': 'Failed base',
  'FAIL-EMA20': 'EMA 20 failure',
  'FAIL-SMA50': 'SMA 50 failure',
  'FAIL-STRUCT': 'Structural failure',
}

function groupForPatternType(value) {
  if (value?.startsWith('REV-')) return 'REVERSAL'
  if (value?.startsWith('HARM-')) return 'HARMONIC'
  if (value?.startsWith('CONT-')) return 'CONTINUATION'
  return 'SETUP'
}

function initialValue(name, allowed, fallback = '') {
  const value = new URLSearchParams(window.location.search).get(name) || fallback
  return allowed.includes(value) ? value : fallback
}

export default function PatternScannerPage({ onNavigate, onUnauthorized }) {
  useDocumentTitle('Pattern scanner')
  const [timeframe, setTimeframe] = useState(() => initialValue('timeframe', TIMEFRAMES.map((item) => item.value), '1D'))
  const [patternGroup, setPatternGroup] = useState(() => initialValue('patternGroup', GROUPS.map((item) => item.value)))
  const [patternType, setPatternType] = useState(() => new URLSearchParams(window.location.search).get('patternType') || '')
  const [direction, setDirection] = useState(() => initialValue('direction', ['', 'BULLISH', 'BEARISH', 'NEUTRAL']))
  const query = useMemo(() => ({
    pageSize: 25,
    sort: 'setupScore',
    direction: 'desc',
    timeframe,
    ...(patternGroup ? { patternGroup } : {}),
    ...(patternType ? { patternType } : {}),
    ...(direction ? { patternDirection: direction } : {}),
  }), [timeframe, patternGroup, patternType, direction])
  const queryString = useMemo(() => new URLSearchParams({
    timeframe,
    ...(patternGroup ? { patternGroup } : {}),
    ...(patternType ? { patternType } : {}),
    ...(direction ? { direction } : {}),
  }).toString(), [timeframe, patternGroup, patternType, direction])
  const resource = useApiResource(
    `pattern-scanner:${queryString}`,
    (signal) => getPatterns(query, { signal, onUnauthorized }),
  )
  const updateView = (next) => {
    const values = { timeframe, patternGroup, patternType, direction, ...next }
    setTimeframe(values.timeframe)
    setPatternGroup(values.patternGroup)
    setPatternType(values.patternType)
    setDirection(values.direction)
    const params = new URLSearchParams({
      timeframe: values.timeframe,
      ...(values.patternGroup ? { patternGroup: values.patternGroup } : {}),
      ...(values.patternType ? { patternType: values.patternType } : {}),
      ...(values.direction ? { direction: values.direction } : {}),
    })
    onNavigate(`/pattern-scanner?${params}`, { replace: true })
  }
  const timeframeLabel = TIMEFRAMES.find((item) => item.value === timeframe)?.label || timeframe

  return <>
    <PageIntro eyebrow='Explore patterns' title='Pattern scanner' description='Find active daily, weekly, and monthly chart patterns, then open any result to see why it qualified.' date={resource.data?.dataAsOf} />
    <section className='scanner-panel' aria-label='Pattern scanner controls'>
      <div><p className='eyebrow'>Timeframe</p><h2>Select a completed chart interval</h2></div>
      <div className='scanner-tabs' role='tablist' aria-label='Chart timeframe'>{TIMEFRAMES.map((item) => <button key={item.value} type='button' role='tab' aria-selected={timeframe === item.value} className={timeframe === item.value ? 'is-active' : ''} onClick={() => updateView({ timeframe: item.value })}><strong>{item.label}</strong><small>{item.detail}</small></button>)}</div>
      <div className='scanner-filters'>
        <label>Pattern family<select className='select-control' value={patternGroup} onChange={(event) => updateView({ patternGroup: event.target.value, patternType: '' })}>{GROUPS.map((group) => <option key={group.value || 'all'} value={group.value}>{group.label}</option>)}</select></label>
        <label>Pattern type<select className='select-control' value={patternType} onChange={(event) => updateView({ patternType: event.target.value })}><option value=''>All supported types</option>{(resource.data?.facets?.patternTypes || []).filter((item) => !patternGroup || groupForPatternType(item.value) === patternGroup).map((item) => <option key={item.value} value={item.value} disabled={!item.count}>{PATTERN_TYPE_LABELS[item.value] || labelize(item.value)} ({item.count || 'no current matches'})</option>)}</select></label>
        <label>Direction<select className='select-control' value={direction} onChange={(event) => updateView({ direction: event.target.value })}><option value=''>All directions</option><option value='BULLISH'>Bullish</option><option value='BEARISH'>Bearish</option><option value='NEUTRAL'>Neutral</option></select></label>
      </div>
    </section>
    <ResourceState status={resource.status} error={resource.error} onRetry={resource.reload}>
      {resource.data && <section aria-labelledby='scanner-results'><div className='section-heading'><div><p className='eyebrow'>{timeframeLabel} view</p><h2 id='scanner-results'>Active patterns</h2></div><p>{resource.data.totalCount || 0} patterns found.</p></div>{resource.data.items?.length ? <div className='setup-grid'>{resource.data.items.map((setup) => <SetupCard key={setup.patternInstanceId} setup={setup} onNavigate={onNavigate} />)}</div> : <EmptyState title={`No active ${timeframeLabel.toLowerCase()} patterns`} message='Try another pattern family, direction, or timeframe.' />}</section>}
    </ResourceState>
    <details className='scanner-library'>
      <summary><span><span className='eyebrow'>Detection library</span><strong>View pattern coverage</strong></span><span>Implemented and planned families</span></summary>
      <div className='scanner-library__grid'>{LIBRARY.map(([family, status, patterns]) => <article key={family}><div className='scanner-library__title'><h3>{family}</h3><span>{status}</span></div><div className='tag-list'>{patterns.map((pattern) => <span key={pattern}>{pattern}</span>)}</div></article>)}</div>
    </details>
  </>
}

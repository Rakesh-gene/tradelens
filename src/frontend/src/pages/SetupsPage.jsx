import React, { useState } from 'react'
import { apiGet } from '../apiClient.js'
import useApiResource from '../useApiResource.js'
import { PageIntro, ResourceState, SetupCard } from '../components/PatternUi.jsx'

const FILTER_NAMES = ['state', 'patternClass', 'patternType', 'variant', 'minSetupScore', 'sector', 'minRs6m', 'minLiquidityScore', 'sort']
const EMPTY_FILTERS = { state: '', patternClass: '', patternType: '', variant: '', minSetupScore: '', sector: '', minRs6m: '', minLiquidityScore: '', sort: 'setupScore' }

function filtersFromLocation() {
  const query = new URLSearchParams(window.location.search)
  return Object.fromEntries(FILTER_NAMES.map((name) => [name, query.get(name) || EMPTY_FILTERS[name]]))
}

export default function SetupsPage({ onNavigate, onUnauthorized }) {
  const initial = new URLSearchParams(window.location.search)
  const [filters, setFilters] = useState(filtersFromLocation)
  const [cursor, setCursor] = useState(initial.get('cursor') || '')
  const query = new URLSearchParams({ pageSize: '25', sort: filters.sort, direction: 'desc' })
  Object.entries(filters).forEach(([key, value]) => value && key !== 'sort' && query.set(key, value))
  if (cursor) query.set('cursor', cursor)
  const key = query.toString()
  const resource = useApiResource(key, (signal) => apiGet(`/api/setups?${key}`, { signal, onUnauthorized }))

  const writeUrl = (nextCursor = '') => {
    const url = new URLSearchParams()
    Object.entries(filters).forEach(([name, value]) => value && url.set(name, value))
    if (nextCursor) url.set('cursor', nextCursor)
    window.history.replaceState({}, '', `/setups${url.size ? `?${url}` : ''}`)
  }
  const apply = (event) => { event.preventDefault(); setCursor(''); writeUrl() }
  const clear = () => { setFilters(EMPTY_FILTERS); setCursor(''); window.history.replaceState({}, '', '/setups') }
  const nextPage = () => { const next = resource.data.nextCursor; setCursor(next); writeUrl(next) }
  const firstPage = () => { setCursor(''); writeUrl() }
  const change = (name) => (event) => setFilters({ ...filters, [name]: event.target.value })

  return <>
    <PageIntro eyebrow="Setup screener" title="Find structure, then inspect evidence." description="Filter the active pattern universe without downloading it into the browser." />
    <form className="filter-bar" onSubmit={apply}>
      <label>Lifecycle state<select value={filters.state} onChange={change('state')}><option value="">All states</option>{['FORMING', 'MATURE', 'READY', 'TRIGGERED', 'CONFIRMED', 'FAILED', 'INVALIDATED'].map((value) => <option key={value}>{value}</option>)}</select></label>
      <label>Pattern family<select value={filters.patternClass} onChange={change('patternClass')}><option value="">All families</option>{['BASE', 'BREAKOUT', 'PULLBACK', 'TREND', 'COMPRESSION', 'MOMENTUM', 'FAILURE'].map((value) => <option key={value}>{value}</option>)}</select></label>
      <label>Pattern type<input value={filters.patternType} onChange={change('patternType')} placeholder="For example VCP" /></label>
      <label>Variant<input value={filters.variant} onChange={change('variant')} placeholder="Any variant" /></label>
      <label>Minimum setup score<input type="number" min="0" max="100" value={filters.minSetupScore} onChange={change('minSetupScore')} /></label>
      <label>Sector<input value={filters.sector} onChange={change('sector')} placeholder="Sector code" list="sector-options" /><datalist id="sector-options">{(resource.data?.facets?.sectors || []).map((sector) => <option key={sector.value} value={sector.value}>{sector.label || sector.value}</option>)}</datalist></label>
      <label>Minimum RS 6M<input type="number" min="0" max="100" value={filters.minRs6m} onChange={change('minRs6m')} /></label>
      <label>Minimum liquidity<input type="number" min="0" max="100" value={filters.minLiquidityScore} onChange={change('minLiquidityScore')} /></label>
      <label>Rank by<select value={filters.sort} onChange={change('sort')}><option value="setupScore">Setup score</option><option value="qualityScore">Quality</option><option value="maturityScore">Maturity</option><option value="detectedDate">Detected date</option><option value="distanceToPivotPct">Distance to pivot</option></select></label>
      <div className="filter-actions"><button className="primary-button" type="submit">Apply</button><button className="secondary-button" type="button" onClick={clear}>Clear</button></div>
    </form>
    <p className="ranking-note">Ranking score, not historical probability.</p>
    <ResourceState status={resource.status} error={resource.error} onRetry={resource.reload}>
      {resource.data && <>
        <p className="result-status" aria-live="polite">{resource.data.items.length} securities on this page · each card groups its active signals</p>
        {resource.data.items.length
          ? <div className="setup-grid">{resource.data.items.map((setup) => <SetupCard key={setup.patternInstanceId} setup={setup} onNavigate={onNavigate} />)}</div>
          : <div className="empty-panel"><h2>No matching setups</h2><p>Clear filters or choose another lifecycle state.</p></div>}
        <div className="pagination"><button className="secondary-button" type="button" disabled={!cursor} onClick={firstPage}>First page</button><button className="secondary-button" type="button" disabled={!resource.data.nextCursor} onClick={nextPage}>Next page</button></div>
      </>}
    </ResourceState>
  </>
}

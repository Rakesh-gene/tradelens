import React, { useEffect, useMemo, useState } from 'react'
import { getSetups } from '../api/marketApi.js'
import useApiResource from '../useApiResource.js'
import { PageIntro, SetupCard } from '../components/PatternUi.jsx'
import PatternFilters from '../components/PatternFilters.jsx'
import SetupTable from '../components/SetupTable.jsx'
import PaginationControls from '../components/PaginationControls.jsx'
import { EmptyState, ResourceState } from '../components/ResourceStates.jsx'
import useMediaQuery from '../hooks/useMediaQuery.js'
import useDocumentTitle from '../hooks/useDocumentTitle.js'
import { EMPTY_SETUP_FILTERS, parseSetupFilters, setupQuery } from '../utils/setupFilters.js'
import { withQuery } from '../utils/queryString.js'

export default function SetupsPage({ onNavigate, onUnauthorized }) {
  useDocumentTitle('Setups')
  const parsed = useMemo(() => parseSetupFilters(window.location.search), [])
  const [filters, setFilters] = useState(parsed.filters)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const compact = useMediaQuery('(max-width: 980px)')
  const requestQuery = setupQuery(parsed.filters, parsed.cursor)
  const key = withQuery('/api/setups', requestQuery)
  const resource = useApiResource(key, (signal) => getSetups(requestQuery, { signal, onUnauthorized }))

  const destination = (nextFilters, cursor = '') => withQuery('/setups', setupQuery(nextFilters, cursor))
  useEffect(() => {
    if (parsed.corrected.length) onNavigate(destination(parsed.filters, parsed.cursor), { replace: true })
  }, [])
  const change = (name, value) => setFilters((current) => ({ ...current, [name]: value }))
  const apply = (event) => { event.preventDefault(); setDrawerOpen(false); onNavigate(destination(filters)) }
  const clear = () => { setFilters({ ...EMPTY_SETUP_FILTERS }); setDrawerOpen(false); onNavigate('/setups') }
  const sort = (name) => {
    const direction = parsed.filters.sort === name && parsed.filters.direction === 'desc' ? 'asc' : 'desc'
    onNavigate(destination({ ...parsed.filters, sort: name, direction }))
  }

  return <>
    <PageIntro eyebrow="Opportunity intelligence" title="Find the best fit within every lifecycle stage." description="Compare active setups against peers in the same stage, then inspect the evidence behind the rank." date={resource.data?.dataAsOf || parsed.filters.asOf} />
    {parsed.corrected.length > 0 && <p className="status-banner" role="status">Unsupported {parsed.corrected.join(', ')} filters were removed.</p>}
    {compact ? <><button className="secondary-button filter-open" type="button" onClick={() => setDrawerOpen(true)}>Filters and sorting</button><PatternFilters drawer open={drawerOpen} filters={filters} facets={resource.data?.facets} onChange={change} onApply={apply} onClear={clear} onClose={() => setDrawerOpen(false)} /></> : <PatternFilters filters={filters} facets={resource.data?.facets} onChange={change} onApply={apply} onClear={clear} />}
    <p className="ranking-note">Best fit combines setup evidence, context, and liquidity, then ranks each security against peers in the same lifecycle state. It is not historical probability.</p>
    <ResourceState status={resource.status} error={resource.error} onRetry={resource.reload}>
      {resource.data && <>
        <p className="result-status" aria-live="polite">{resource.data.items.length} securities on this page · sorted {parsed.filters.direction === 'desc' ? 'highest' : 'lowest'} first by {parsed.filters.sort}</p>
        {resource.data.items.length ? (compact
          ? <div className="setup-grid">{resource.data.items.map((setup) => <SetupCard key={setup.patternInstanceId} setup={setup} onNavigate={onNavigate} />)}</div>
          : <SetupTable items={resource.data.items} filters={parsed.filters} onSort={sort} onNavigate={onNavigate} />)
          : <EmptyState title="No matching setups" message="Clear filters, change the market date, or choose another lifecycle state." action={<button className="secondary-button" type="button" onClick={clear}>Clear filters</button>} />}
        <PaginationControls busy={resource.status === 'refreshing'} hasPrevious={Boolean(parsed.cursor)} hasNext={Boolean(resource.data.nextCursor)} onPrevious={() => onNavigate(destination(parsed.filters))} onNext={() => onNavigate(destination(parsed.filters, resource.data.nextCursor))} />
      </>}
    </ResourceState>
  </>
}

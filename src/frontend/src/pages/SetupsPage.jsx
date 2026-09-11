import React, { useEffect, useMemo, useState } from 'react'
import { getSetups } from '../api/marketApi.js'
import useApiResource from '../useApiResource.js'
import { PageIntro, SetupCard } from '../components/PatternUi.jsx'
import PatternFilters from '../components/PatternFilters.jsx'
import { EmptyState, ResourceState } from '../components/ResourceStates.jsx'
import useMediaQuery from '../hooks/useMediaQuery.js'
import useDocumentTitle from '../hooks/useDocumentTitle.js'
import { EMPTY_SETUP_FILTERS, parseSetupFilters, setupQuery } from '../utils/setupFilters.js'
import { withQuery } from '../utils/queryString.js'

const setupPageCache = new Map()

function rememberSetupPage(key, page) {
  setupPageCache.delete(key)
  setupPageCache.set(key, page)
  if (setupPageCache.size > 12) setupPageCache.delete(setupPageCache.keys().next().value)
}

export default function SetupsPage({ onNavigate, onUnauthorized }) {
  useDocumentTitle('Setups')
  const parsed = useMemo(() => parseSetupFilters(window.location.search), [])
  const [filters, setFilters] = useState(parsed.filters)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const compact = useMediaQuery('(max-width: 980px)')
  const requestQuery = setupQuery(parsed.filters)
  const key = withQuery('/api/setups', requestQuery)
  const cachedPage = setupPageCache.get(key)
  const [items, setItems] = useState(cachedPage?.items || [])
  const [nextCursor, setNextCursor] = useState(cachedPage?.nextCursor || '')
  const [totalCount, setTotalCount] = useState(cachedPage?.totalCount || 0)
  const [loadingMore, setLoadingMore] = useState(false)
  const [loadMoreError, setLoadMoreError] = useState('')
  const resource = useApiResource(key, (signal) => getSetups(requestQuery, { signal, onUnauthorized }))

  const destination = (nextFilters) => withQuery('/setups', setupQuery(nextFilters))
  useEffect(() => {
    if (parsed.corrected.length || parsed.cursor) onNavigate(destination(parsed.filters), { replace: true })
  }, [])
  useEffect(() => {
    if (!resource.data) return
    const firstPage = resource.data.items || []
    const freshTotal = Number(resource.data.totalCount || firstPage.length || 0)
    const cached = setupPageCache.get(key)
    const sameHead = cached && firstPage.every(
      (item, index) => cached.items[index]?.patternInstanceId === item.patternInstanceId
    )
    const page = sameHead && cached.totalCount === freshTotal
      ? cached
      : { items: firstPage, nextCursor: resource.data.nextCursor || '', totalCount: freshTotal }
    setItems(page.items)
    setNextCursor(page.nextCursor)
    setTotalCount(page.totalCount)
    rememberSetupPage(key, page)
    setLoadMoreError('')
  }, [resource.data])

  const change = (name, value) => setFilters((current) => ({ ...current, [name]: value }))
  const apply = (event) => { event.preventDefault(); setDrawerOpen(false); onNavigate(destination(filters)) }
  const clear = () => { setFilters({ ...EMPTY_SETUP_FILTERS }); setDrawerOpen(false); onNavigate('/setups') }
  const showMore = async () => {
    if (!nextCursor || loadingMore) return
    setLoadingMore(true)
    setLoadMoreError('')
    try {
      const page = await getSetups(setupQuery(parsed.filters, nextCursor), { onUnauthorized })
      setItems((current) => {
        const known = new Set(current.map((item) => item.patternInstanceId))
        const combined = [...current, ...(page.items || []).filter((item) => !known.has(item.patternInstanceId))]
        rememberSetupPage(key, {
          items: combined,
          nextCursor: page.nextCursor || '',
          totalCount: Number(page.totalCount || totalCount),
        })
        return combined
      })
      setNextCursor(page.nextCursor || '')
      setTotalCount(Number(page.totalCount || totalCount))
    } catch (error) {
      setLoadMoreError(error.message || 'Could not load more setups.')
    } finally {
      setLoadingMore(false)
    }
  }
  const remainingCount = Math.max(0, totalCount - items.length)
  const nextBatchCount = Math.min(25, remainingCount)

  return <>
    <PageIntro title="Setups" date={resource.data?.dataAsOf || parsed.filters.asOf} />
    {parsed.corrected.length > 0 && <p className="status-banner" role="status">Unsupported {parsed.corrected.join(', ')} filters were removed.</p>}
    {compact ? <><button className="secondary-button filter-open" type="button" onClick={() => setDrawerOpen(true)}>Filters and sorting</button><PatternFilters drawer open={drawerOpen} filters={filters} facets={resource.data?.facets} onChange={change} onApply={apply} onClear={clear} onClose={() => setDrawerOpen(false)} /></> : <PatternFilters filters={filters} facets={resource.data?.facets} onChange={change} onApply={apply} onClear={clear} />}
    <p className="ranking-note">Scores rank setups within the same lifecycle state; they do not predict returns.</p>
    <ResourceState status={resource.status} error={resource.error} onRetry={resource.reload}>
      {resource.data && <>
        <p className="result-status" aria-live="polite">Showing {items.length} of {totalCount} securities · sorted {parsed.filters.direction === 'desc' ? 'highest' : 'lowest'} first by {parsed.filters.sort}</p>
        {items.length
          ? <div className="setup-grid">{items.map((setup) => <SetupCard key={setup.patternInstanceId} setup={setup} onNavigate={onNavigate} />)}</div>
          : <EmptyState title="No matching setups" message="Clear filters, change the market date, or choose another lifecycle state." action={<button className="secondary-button" type="button" onClick={clear}>Clear filters</button>} />}
        {loadMoreError && <p className="status-banner" role="alert">{loadMoreError}</p>}
        {nextCursor && remainingCount > 0 && <div className="setup-load-more">
          <button className="secondary-button" type="button" disabled={loadingMore} onClick={showMore}>
            {loadingMore ? 'Loading…' : `Show ${nextBatchCount} more`}
          </button>
          <span>{remainingCount} remaining</span>
        </div>}
      </>}
    </ResourceState>
  </>
}

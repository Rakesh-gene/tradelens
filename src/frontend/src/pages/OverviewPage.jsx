import React, { useEffect, useRef, useState } from 'react'
import { getOverview } from '../api/marketApi.js'
import useApiResource from '../useApiResource.js'
import { PageIntro, SetupCard } from '../components/PatternUi.jsx'
import MarketRegimeCard from '../components/MarketRegimeCard.jsx'
import { EmptyState, ResourceState } from '../components/ResourceStates.jsx'
import useDocumentTitle from '../hooks/useDocumentTitle.js'
import NavigationLink from '../components/NavigationLink.jsx'

async function loadQualifiedOverview(query, options) {
  const page = await getOverview(query, options)
  if (!page.qualification) throw new Error('Overview qualification is unavailable. Restart the backend with the updated code.')
  return page
}

export default function OverviewPage({ onNavigate, onUnauthorized }) {
  useDocumentTitle('Overview')
  const resource = useApiResource('overview', (signal) => loadQualifiedOverview({ top: 6 }, { signal, onUnauthorized }))
  const [setups, setSetups] = useState([])
  const [nextCursor, setNextCursor] = useState(null)
  const [loadingMore, setLoadingMore] = useState(false)
  const [loadMoreError, setLoadMoreError] = useState(null)
  const [qualifiedCount, setQualifiedCount] = useState(0)
  const request = useRef(null)
  useEffect(() => {
    setSetups(resource.data?.topSetups || [])
    setNextCursor(resource.data?.nextCursor || null)
    setQualifiedCount(resource.data?.qualification?.qualifiedCount || 0)
    setLoadingMore(false)
    setLoadMoreError(null)
    return () => { request.current?.abort(); request.current = null }
  }, [resource.data])
  const loadMore = async () => {
    if (!nextCursor || request.current || resource.status !== 'success') return
    const controller = new AbortController()
    request.current = controller
    setLoadingMore(true)
    setLoadMoreError(null)
    try {
      const page = await loadQualifiedOverview({ top: 6, asOf: resource.data.dataAsOf, cursor: nextCursor }, { signal: controller.signal, onUnauthorized })
      if (controller.signal.aborted || request.current !== controller) return
      if (page.qualification?.configurationVersion !== resource.data.qualification?.configurationVersion) {
        throw new Error('Qualification rules changed. Refresh Overview before loading more setups.')
      }
      setSetups((current) => {
        const known = new Set(current.map((setup) => setup.patternInstanceId))
        return [...current, ...page.topSetups.filter((setup) => !known.has(setup.patternInstanceId))]
      })
      setNextCursor(page.nextCursor || null)
      if (page.qualification) setQualifiedCount(page.qualification.qualifiedCount)
    } catch (error) {
      if (!controller.signal.aborted && request.current === controller) setLoadMoreError(error.message || 'Could not load more setups.')
    } finally {
      if (request.current === controller) { request.current = null; setLoadingMore(false) }
    }
  }
  return <>
    <PageIntro eyebrow="Today’s market" title="Market overview" description="See market direction, breadth, and the strongest active setups at a glance." date={resource.data?.dataAsOf} />
    <ResourceState status={resource.status} error={resource.error} onRetry={resource.reload}>
    {resource.data && <>
      <section className="market-grid" aria-label="Market regime and lifecycle"><MarketRegimeCard market={resource.data.market} /><div className="state-counts">{Object.entries(resource.data.countsByState).map(([state, count]) => <NavigationLink key={state} to={`/setups?state=${state}`} onNavigate={onNavigate}><span>{state}</span><strong>{count}</strong><small>View setups →</small></NavigationLink>)}</div></section>
      <section className="section-heading"><div><h2>Highest-ranked setups</h2></div><NavigationLink className="secondary-button" to="/setups" onNavigate={onNavigate}>View all setups</NavigationLink></section>
      {setups.length ? <div className="setup-grid" aria-busy={loadingMore}>{setups.map((setup) => <div key={setup.patternInstanceId} className="overview-qualified-setup">
        <SetupCard setup={setup} onNavigate={onNavigate} />
        {!!setup.decision?.cautions?.length && <p className="overview-qualification">Caution: {setup.decision.cautions.join('; ')}.</p>}
      </div>)}</div> : <EmptyState title="No qualifying setups" message="No setups meet the Overview qualification rules for this evidence date. View all setups to explore the broader universe." />}
      {loadMoreError && <p className="status-banner" role="alert">{loadMoreError}</p>}
      {setups.length > 0 && <div className="setup-load-more">
        {nextCursor && <button className="secondary-button" type="button" disabled={loadingMore || resource.status !== 'success'} onClick={loadMore}>{loadingMore ? 'Loading…' : loadMoreError ? 'Retry load more' : 'Load more'}</button>}
        <span role="status">Showing {setups.length} of {qualifiedCount} qualified setups</span>
      </div>}
    </>}
    </ResourceState>
  </>
}

import React from 'react'
import { getOverview } from '../api/marketApi.js'
import useApiResource from '../useApiResource.js'
import { PageIntro, SetupCard } from '../components/PatternUi.jsx'
import MarketRegimeCard from '../components/MarketRegimeCard.jsx'
import { EmptyState, ResourceState } from '../components/ResourceStates.jsx'
import useDocumentTitle from '../hooks/useDocumentTitle.js'
import NavigationLink from '../components/NavigationLink.jsx'

export default function OverviewPage({ onNavigate, onUnauthorized }) {
  useDocumentTitle('Overview')
  const resource = useApiResource('overview', (signal) => getOverview({ top: 6 }, { signal, onUnauthorized }))
  return <>
    <PageIntro eyebrow="Today’s market" title="Market overview" description="See market direction, breadth, and the strongest active setups at a glance." date={resource.data?.dataAsOf} />
    <ResourceState status={resource.status} error={resource.error} onRetry={resource.reload}>
    {resource.data && <>
      <section className="market-grid" aria-label="Market regime and lifecycle"><MarketRegimeCard market={resource.data.market} /><div className="state-counts">{Object.entries(resource.data.countsByState).map(([state, count]) => <NavigationLink key={state} to={`/setups?state=${state}`} onNavigate={onNavigate}><span>{state}</span><strong>{count}</strong><small>View setups →</small></NavigationLink>)}</div></section>
      <section className="section-heading"><div><h2>Highest-ranked setups</h2></div><NavigationLink className="secondary-button" to="/setups" onNavigate={onNavigate}>View all setups</NavigationLink></section>
      {resource.data.topSetups.length ? <div className="setup-grid">{resource.data.topSetups.map((setup) => <SetupCard key={setup.patternInstanceId} setup={setup} onNavigate={onNavigate} />)}</div> : <EmptyState title="No active opportunities" message="The latest completed scan did not find setups matching the overview states." />}
    </>}
    </ResourceState>
  </>
}

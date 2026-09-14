import React from 'react'
import { getCaseStudies } from '../api/caseStudyApi.js'
import useApiResource from '../useApiResource.js'
import { EmptyState, ResourceState } from '../components/ResourceStates.jsx'
import { PageIntro } from '../components/PatternUi.jsx'
import NavigationLink from '../components/NavigationLink.jsx'
import { formatMarketDate, formatPrice, formatPercent, labelize } from '../utils/formatters.js'
import { describePattern } from '../utils/patternDescriptions.js'

export default function CaseStudiesPage({ onNavigate, onUnauthorized }) {
  const query = new URLSearchParams(window.location.search)
  const view = query.get('view') === 'list' ? 'list' : 'tiles'
  const cursor = query.get('cursor') || ''
  const resource = useApiResource(`${view}:${cursor}`, (signal) => getCaseStudies({ cursor: cursor || undefined, pageSize: 25 }, { signal, onUnauthorized }))
  const changeView = (next) => onNavigate(`/case-studies?view=${next}`, { replace: true })
  const page = (nextCursor) => {
    const next = new URLSearchParams({ view })
    if (nextCursor) next.set('cursor', nextCursor)
    onNavigate(`/case-studies?${next}`)
  }

  return <section className="page-stack">
    <PageIntro eyebrow="Learn from history" title="Stock case studies" description="See why a pattern qualified and how the stock moved over the next 3 months, 6 months, and 1 year." />
    <div className="case-study-catalog-toolbar">
      <p>Choose a case study to open its chart, entry rationale, and forward performance.</p>
      <div className="watchlist-view-switch" role="group" aria-label="Case-study layout">
        <button type="button" aria-pressed={view === 'tiles'} onClick={() => changeView('tiles')}>Tiles</button>
        <button type="button" aria-pressed={view === 'list'} onClick={() => changeView('list')}>List</button>
      </div>
    </div>
    <ResourceState status={resource.status} error={resource.error} onRetry={resource.reload}>{resource.data && <>
      <p className="refresh-status" role="status">{resource.data.items.length} case studies shown{resource.data.dataAsOf ? `. Data as of ${formatMarketDate(resource.data.dataAsOf)}.` : '.'}</p>
      {resource.data.items.length === 0 ? <EmptyState title="No published case studies yet" message="Reviewed case studies will appear here when they are published." /> : <div className={`case-study-catalog case-study-catalog--${view}`}>{resource.data.items.map((item) => <CaseStudyItem key={item.caseStudyId} item={item} onNavigate={onNavigate} />)}</div>}
      {(cursor || resource.data.nextCursor) && <nav className="pagination-controls" aria-label="Case-study pages"><button className="secondary-button" type="button" disabled={!cursor} onClick={() => page('')}>First page</button><button className="secondary-button" type="button" disabled={!resource.data.nextCursor} onClick={() => page(resource.data.nextCursor)}>Next page</button></nav>}
    </>}</ResourceState>
  </section>
}

function CaseStudyItem({ item, onNavigate }) {
  const pattern = describePattern(item.patternType)
  const performance = item.positionalPerformance?.horizons || {}
  return <NavigationLink className="case-study-catalog-item" to={`/case-studies/${encodeURIComponent(item.caseStudyId)}`} onNavigate={onNavigate}>
    <article>
      <div><p className="eyebrow">{labelize(item.state || 'DETECTED')} · {item.timeframe}</p><h2>{item.symbol || item.isin}</h2><p>{item.companyName || 'Historical stock case'}</p></div>
      <div className="case-study-catalog-pattern"><strong>{pattern.label}</strong><small>{item.patternType}</small></div>
      <dl><div><dt>Detected</dt><dd>{formatMarketDate(item.detectionDate)}</dd></div><div><dt>Entry anchor</dt><dd>{formatMarketDate(item.entryDate)} · {formatPrice(item.entryPrice)}</dd></div></dl>
      <div className="case-study-catalog-performance">{['3M', '6M', '1Y'].map((horizon) => <span key={horizon}><small>{horizon}</small><strong>{performance[horizon]?.complete ? formatPercent(performance[horizon].returnPct, { signed: true }) : 'Pending'}</strong></span>)}</div>
      <span className="text-button">Open case study →</span>
    </article>
  </NavigationLink>
}

import React, { useState } from 'react'
import { getCaseStudies } from '../api/caseStudyApi.js'
import useApiResource from '../useApiResource.js'
import { EmptyState, ResourceState } from '../components/ResourceStates.jsx'
import { PageIntro } from '../components/PatternUi.jsx'
import NavigationLink from '../components/NavigationLink.jsx'
import { formatMarketDate, formatPrice, formatPercent, labelize } from '../utils/formatters.js'
import { describePattern } from '../utils/patternDescriptions.js'
import { deleteCaseStudy } from '../api/adminApi.js'
import ConfirmDialog from '../components/ConfirmDialog.jsx'

export default function CaseStudiesPage({ onNavigate, onUnauthorized, isAdmin = false }) {
  const query = new URLSearchParams(window.location.search)
  const view = query.get('view') === 'list' ? 'list' : 'tiles'
  const cursor = query.get('cursor') || ''
  const resource = useApiResource(`${view}:${cursor}`, (signal) => getCaseStudies({ cursor: cursor || undefined, pageSize: 25 }, { signal, onUnauthorized }))
  const [deleting, setDeleting] = useState('')
  const [deleteCandidate, setDeleteCandidate] = useState('')
  const [deleteError, setDeleteError] = useState('')
  const changeView = (next) => onNavigate(`/case-studies?view=${next}`, { replace: true })
  const page = (nextCursor) => {
    const next = new URLSearchParams({ view })
    if (nextCursor) next.set('cursor', nextCursor)
    onNavigate(`/case-studies?${next}`)
  }
  const remove = async (caseStudyId) => {
    setDeleting(caseStudyId); setDeleteError('')
    try { await deleteCaseStudy(caseStudyId, { onUnauthorized }); setDeleteCandidate(''); resource.reload() }
    catch (error) { setDeleteError(error.message || 'Could not delete this case study.') }
    finally { setDeleting('') }
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
      {deleteError && <p className="form-message error" role="alert">{deleteError}</p>}
      <p className="refresh-status" role="status">{resource.data.items.length} case studies shown{resource.data.dataAsOf ? `. Data as of ${formatMarketDate(resource.data.dataAsOf)}.` : '.'}</p>
      {resource.data.items.length === 0 ? <EmptyState title="No published case studies yet" message="Reviewed case studies will appear here when they are published." /> : <div className={`case-study-catalog case-study-catalog--${view}`}>{resource.data.items.map((item) => <CaseStudyItem key={item.caseStudyId} item={item} onNavigate={onNavigate} isAdmin={isAdmin} deleting={deleting === item.caseStudyId} onDelete={setDeleteCandidate} />)}</div>}
      {(cursor || resource.data.nextCursor) && <nav className="pagination-controls" aria-label="Case-study pages"><button className="secondary-button" type="button" disabled={!cursor} onClick={() => page('')}>First page</button><button className="secondary-button" type="button" disabled={!resource.data.nextCursor} onClick={() => page(resource.data.nextCursor)}>Next page</button></nav>}
    </>}<ConfirmDialog open={Boolean(deleteCandidate)} title="Delete this case study?" message="This permanently removes the case study and its recorded performance. This cannot be undone." busy={Boolean(deleting)} onCancel={() => setDeleteCandidate('')} onConfirm={() => remove(deleteCandidate)} /></ResourceState>
  </section>
}

function CaseStudyItem({ item, onNavigate, isAdmin, deleting, onDelete }) {
  const pattern = describePattern(item.patternType)
  const performance = item.positionalPerformance?.horizons || {}
  return <article className="case-study-catalog-item">
    <NavigationLink className="case-study-catalog-item__open" to={`/case-studies/${encodeURIComponent(item.caseStudyId)}`} onNavigate={onNavigate}>
      <div><p className="eyebrow">{labelize(item.state || 'DETECTED')} · {item.timeframe}</p><h2>{item.symbol || item.isin}</h2><p>{item.companyName || 'Historical stock case'}</p></div>
      <div className="case-study-catalog-pattern"><strong>{pattern.label}</strong><small>{item.patternType}</small></div>
      <dl><div><dt>Detected</dt><dd>{formatMarketDate(item.detectionDate)}</dd></div><div><dt>Entry anchor</dt><dd>{formatMarketDate(item.entryDate)} · {formatPrice(item.entryPrice)}</dd></div></dl>
      <div className="case-study-catalog-performance">{['3M', '6M', '1Y'].map((horizon) => <span key={horizon}><small>{horizon}</small><strong>{performance[horizon]?.complete ? formatPercent(performance[horizon].returnPct, { signed: true }) : 'Pending'}</strong></span>)}</div>
      <span className="text-button">Open case study →</span>
    </NavigationLink>
    {isAdmin && <DeleteCaseButton deleting={deleting} onClick={() => onDelete(item.caseStudyId)} />}
  </article>
}

function DeleteCaseButton({ deleting, onClick }) {
  return <button className="case-study-delete" type="button" disabled={deleting} onClick={onClick} aria-label={deleting ? 'Deleting case study' : 'Delete case study'} title={deleting ? 'Deleting case study' : 'Delete case study'}>
    <svg aria-hidden="true" viewBox="0 0 24 24" fill="none"><path d="M4 7h16M9.5 11v5M14.5 11v5M9 7l.7-2h4.6l.7 2M6.5 7l.7 12h10.6l.7-12" /></svg>
  </button>
}

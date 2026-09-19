import React, { useEffect, useState } from 'react'
import { createCaseStudyRun, deleteCaseStudy, getCaseStudyReviewQueue, getCaseStudyRun, getCaseStudyRunItems, getLatestCaseStudyRun, resumeCaseStudyRun, reviewCaseStudy } from '../api/adminApi.js'
import CaseStudyStockPicker from '../components/CaseStudyStockPicker.jsx'
import { PageIntro, StateBadge } from '../components/PatternUi.jsx'
import { buildCaseStudyPath } from '../routing/routes.js'
import { formatMarketDate, formatPercent } from '../utils/formatters.js'
import ConfirmDialog from '../components/ConfirmDialog.jsx'
import { SUPPORTED_PATTERN_TYPES } from '../utils/setupFilters.js'

const terminal = new Set(['COMPLETED', 'PARTIAL', 'FAILED'])
const ranges = [['3M', '3 months'], ['6M', '6 months'], ['1Y', '1 year'], ['3Y', '3 years'], ['5Y', '5 years']]
const activeRunKey = 'tradelensCaseStudyRunId'
const stageLabels = { PREPARING_HISTORY: 'Preparing historical data', REPLAYING_HISTORY: 'Checking historical setups', BUILDING_CASES: 'Creating case studies', COMPLETED: 'Build complete', FAILED: 'Build failed' }

export default function AdminCaseStudyPage({ onNavigate, onUnauthorized }) {
  const [stock, setStock] = useState(null)
  const [lookback, setLookback] = useState('1Y')
  const [run, setRun] = useState(() => {
    const runId = window.sessionStorage.getItem(activeRunKey)
    return runId ? { runId, status: 'PENDING' } : null
  })
  const [items, setItems] = useState([])
  const [reviewQueue, setReviewQueue] = useState([])
  const [publishing, setPublishing] = useState('')
  const [deleting, setDeleting] = useState('')
  const [selectedCaseIds, setSelectedCaseIds] = useState([])
  const [deleteCandidates, setDeleteCandidates] = useState([])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (run?.runId) return undefined
    const controller = new AbortController()
    getLatestCaseStudyRun({ signal: controller.signal, onUnauthorized })
      .then((response) => { if (!controller.signal.aborted && response.run) { window.sessionStorage.setItem(activeRunKey, response.run.runId); setRun(response.run) } })
      .catch((reason) => { if (!controller.signal.aborted && reason.name !== 'AbortError') setError(reason.message) })
    return () => controller.abort()
  }, [run?.runId, onUnauthorized])

  useEffect(() => {
    if (!run?.runId) return undefined
    const controller = new AbortController()
    let inFlight = false
    const refresh = async () => {
      if (inFlight) return
      inFlight = true
      try {
        const status = await getCaseStudyRun(run.runId, { signal: controller.signal, onUnauthorized })
        if (controller.signal.aborted) return
        setRun(status.run)
        const progress = await getCaseStudyRunItems(run.runId, { pageSize: 100 }, { signal: controller.signal, onUnauthorized })
        if (!controller.signal.aborted) setItems(progress.items || [])
      } catch (reason) {
        if (!controller.signal.aborted && reason.status === 404) { window.sessionStorage.removeItem(activeRunKey); setRun(null) }
        else if (!controller.signal.aborted && reason.name !== 'AbortError') setError(reason.message)
      }
      finally { inFlight = false }
    }
    if (!terminal.has(run.status)) {
      refresh()
      const timer = window.setInterval(refresh, 2000)
      return () => { controller.abort(); window.clearInterval(timer) }
    }
    return () => controller.abort()
  }, [run?.runId, run?.status, onUnauthorized])

  useEffect(() => {
    if (run && !terminal.has(run.status)) return undefined
    const controller = new AbortController()
    getCaseStudyReviewQueue({ status: 'PENDING', pageSize: 100 }, { signal: controller.signal, onUnauthorized })
      .then((response) => setReviewQueue(response.items || []))
      .catch((reason) => { if (reason.name !== 'AbortError') setError(reason.message) })
    return () => controller.abort()
  }, [run?.status, onUnauthorized])

  const build = async (selectedStock, selectedLookback) => {
    setError('')
    if (!selectedStock?.isin) { setError('Select a stock from the search results.'); return }
    setBusy(true)
    try {
      const response = await createCaseStudyRun({ isin: selectedStock.isin, lookback: selectedLookback }, { onUnauthorized })
      window.sessionStorage.setItem(activeRunKey, response.run.runId)
      setRun(response.run); setItems([])
    } catch (reason) { setError(reason.message) } finally { setBusy(false) }
  }
  const start = (event) => { event.preventDefault(); build(stock, lookback) }
  const resume = async () => {
    setBusy(true); setError('')
    try { setRun((await resumeCaseStudyRun(run.runId, { onUnauthorized })).run) }
    catch (reason) { setError(reason.message) } finally { setBusy(false) }
  }
  const publish = async (caseStudyId) => {
    setPublishing(caseStudyId); setError('')
    try {
      await reviewCaseStudy(caseStudyId, 'REVIEWED', { onUnauthorized })
      setReviewQueue((current) => current.filter((item) => item.caseStudyId !== caseStudyId))
    } catch (reason) { setError(reason.message) } finally { setPublishing('') }
  }
  const toggleCaseSelection = (caseStudyId) => setSelectedCaseIds((current) => current.includes(caseStudyId)
    ? current.filter((id) => id !== caseStudyId)
    : [...current, caseStudyId])
  const remove = async (caseStudyIds) => {
    const ids = [...new Set(caseStudyIds)]
    if (!ids.length) return
    setDeleting(ids.length === 1 ? ids[0] : 'bulk'); setError('')
    try {
      await Promise.all(ids.map((caseStudyId) => deleteCaseStudy(caseStudyId, { onUnauthorized })))
      setDeleteCandidates([])
      setSelectedCaseIds((current) => current.filter((id) => !ids.includes(id)))
      setReviewQueue((current) => current.filter((item) => !ids.includes(item.caseStudyId)))
    } catch (reason) { setError(reason.message || 'Could not delete the selected case studies.') } finally { setDeleting('') }
  }

  return <section className="page-stack">
    <PageIntro eyebrow="Case study builder" title="Build a stock case study" description="Choose a stock and time period to create historical cases you can inspect and publish." />
    <form className="evidence-card case-study-build-form" onSubmit={start}>
      <CaseStudyStockPicker value={stock} onChange={setStock} onUnauthorized={onUnauthorized} />
      <label>Date range<select className="select-control" value={lookback} onChange={(event) => setLookback(event.target.value)}>{ranges.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
      <div className="filter-actions"><button className="primary-button" disabled={busy || (run && !terminal.has(run.status))} type="submit">{busy ? 'Starting…' : run && !terminal.has(run.status) ? 'Build in progress' : 'Build case study'}</button></div>
    </form>
    {error && <p className="form-message error" role="alert">{error}</p>}
    {run && <section className="evidence-card case-study-run" aria-label="Case-study build status">
      <div className="card-title"><div><p className="eyebrow">Case-study build</p><h2>{run.stock?.symbol || stock?.symbol || 'Selected stock'}</h2></div><StateBadge state={run.status} /></div>
      {run.fromDate && <p>{run.lookback || lookback} of history · {formatMarketDate(run.fromDate)} – {formatMarketDate(run.toDate)}</p>}
      <div className="case-study-run__progress" role="status" aria-live="polite"><strong>{stageLabels[run.stage] || (run.status === 'PENDING' ? 'Starting build' : 'Checking build status')}</strong>{!terminal.has(run.status) && <span>{run.progressPct != null ? `About ${run.progressPct}%` : 'Working…'}</span>}</div>
      {!terminal.has(run.status) && <progress max="100" value={run.progressPct ?? 0} aria-label="Estimated case-study build progress" />}
      {run.stage === 'REPLAYING_HISTORY' && <p className="muted-copy">{run.sessionsProcessed || 0} trading sessions checked{run.lastCompletedSession ? ` · through ${formatMarketDate(run.lastCompletedSession)}` : ''}. Progress is estimated from the date range.</p>}
      {terminal.has(run.status) && <p>{run.casesRecorded || 0} case studies created.{run.status === 'PARTIAL' ? ' Some cases could not be completed.' : ''}</p>}
      {run.status === 'COMPLETED' && !run.caseStudyIds?.length && <p>No supported triggered or confirmed setups were found for this stock in the selected range.</p>}
      {terminal.has(run.status) && run.stock?.isin && <button className="secondary-button" type="button" disabled={busy} onClick={() => build(run.stock, run.lookback)}>Build again</button>}
      {run.failureSummary && Object.keys(run.failureSummary).length > 0 && <p className="form-message error" role="alert">{run.failureSummary.pipeline || Object.values(run.failureSummary).join('; ')}</p>}
      {!!run.caseStudyIds?.length && <div className="case-study-id-list"><h3>Ready to inspect</h3>{run.caseStudyIds.map((id, index) => <button className="secondary-button" type="button" key={id} onClick={() => onNavigate(buildCaseStudyPath(id))}>Inspect case {index + 1}</button>)}</div>}
      {['FAILED', 'PARTIAL'].includes(run.status) && <button className="secondary-button" type="button" disabled={busy} onClick={resume}>Resume build</button>}
      <div className="admin-item-grid">{items.map((item) => <article key={item.isin}><strong>{item.isin}</strong><StateBadge state={item.status} /><p>{item.casesRecorded} cases</p>{item.errorMessage && <small className="admin-item-error">{item.errorMessage}</small>}</article>)}</div>
    </section>}
    <section className="evidence-card case-study-review-queue">
      <div className="card-title"><div><p className="eyebrow">Publication gate</p><h2>Cases awaiting review</h2></div><span className="metric-pill">{reviewQueue.length}</span></div>
      <p>Inspect the chart, entry rationale, and forward stock performance first. Publishing moves the case into the Case Studies catalog.</p>
      {reviewQueue.length === 0 ? <p className="muted-copy">No case studies are awaiting review.</p> : <>
        <div className="case-study-bulk-actions">
          <label><input type="checkbox" checked={reviewQueue.every((item) => selectedCaseIds.includes(item.caseStudyId))} onChange={(event) => setSelectedCaseIds(event.target.checked ? reviewQueue.map((item) => item.caseStudyId) : [])} disabled={Boolean(publishing) || Boolean(deleting)} /> Select all cases</label>
          <button className="case-study-bulk-delete" type="button" disabled={!selectedCaseIds.length || Boolean(publishing) || Boolean(deleting)} onClick={() => setDeleteCandidates(selectedCaseIds)}>Delete selected ({selectedCaseIds.length})</button>
        </div>
        <div className="admin-item-grid">{reviewQueue.map((item) => {
        const publishable = SUPPORTED_PATTERN_TYPES.includes(item.patternType)
        return <article key={item.caseStudyId}>
          <label className="case-study-item-select"><input type="checkbox" checked={selectedCaseIds.includes(item.caseStudyId)} onChange={() => toggleCaseSelection(item.caseStudyId)} disabled={Boolean(publishing) || Boolean(deleting)} aria-label={`Select ${item.symbol || item.caseStudyId}`} /> Select</label>
          <strong>{item.symbol || item.isin}</strong><small>{item.patternType} · {item.timeframe} · {formatMarketDate(item.detectionDate)}</small><p>3M {formatPercent(item.positionalPerformance?.horizons?.['3M']?.returnPct, { signed: true })} · 6M {formatPercent(item.positionalPerformance?.horizons?.['6M']?.returnPct, { signed: true })} · 1Y {formatPercent(item.positionalPerformance?.horizons?.['1Y']?.returnPct, { signed: true })}</p>
          {!publishable && <p className="form-message error">This pattern is not available on the Setups page. Delete this draft; it cannot be published.</p>}
          <div className="case-study-review-actions"><button className="secondary-button" type="button" onClick={() => onNavigate(buildCaseStudyPath(item.caseStudyId))}>Inspect</button><button className="primary-button" type="button" disabled={!publishable || Boolean(publishing) || Boolean(deleting)} onClick={() => publish(item.caseStudyId)}>{publishing === item.caseStudyId ? 'Publishing…' : 'Publish reviewed case'}</button><button className="case-study-delete" type="button" disabled={Boolean(publishing) || Boolean(deleting)} onClick={() => setDeleteCandidates([item.caseStudyId])} aria-label={deleting === item.caseStudyId ? 'Deleting case study' : 'Delete case study'} title={deleting === item.caseStudyId ? 'Deleting case study' : 'Delete case study'}><svg aria-hidden="true" viewBox="0 0 24 24" fill="none"><path d="M4 7h16M9.5 11v5M14.5 11v5M9 7l.7-2h4.6l.7 2M6.5 7l.7 12h10.6l.7-12" /></svg></button></div>
        </article>
      })}</div></>}
    </section>
    <ConfirmDialog open={deleteCandidates.length > 0} title={deleteCandidates.length === 1 ? 'Delete this case study?' : `Delete ${deleteCandidates.length} case studies?`} message={deleteCandidates.length === 1 ? 'This permanently removes the case study and its recorded performance. This cannot be undone.' : 'This permanently removes the selected case studies and their recorded performance. This cannot be undone.'} confirmLabel={deleteCandidates.length === 1 ? 'Delete case' : `Delete ${deleteCandidates.length} cases`} busy={Boolean(deleting)} onCancel={() => setDeleteCandidates([])} onConfirm={() => remove(deleteCandidates)} />
  </section>
}

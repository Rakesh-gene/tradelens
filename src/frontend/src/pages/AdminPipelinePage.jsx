import React, { useEffect, useMemo, useState } from 'react'
import { controlPipelineRun, createPatternScan, createPipelineRun, getAdminEquities, getPipelineRun, getPipelineRuns } from '../api/adminApi.js'
import useApiResource from '../useApiResource.js'
import { PageIntro, ResourceState, StateBadge } from '../components/PatternUi.jsx'
import { formatMarketDate } from '../utils/formatters.js'
import useDocumentTitle from '../hooks/useDocumentTitle.js'
import { buildSecurityPath } from '../routing/routes.js'

const TERMINAL = new Set(['COMPLETED', 'PARTIAL', 'FAILED', 'PAUSED', 'TERMINATED', 'CANCELLED'])
const TIMEFRAMES = ['1D', '1W', '1M']

function isoDate(value) { return value.toISOString().slice(0, 10) }
function defaultFromDate() { const value = new Date(); value.setFullYear(value.getFullYear() - 10); return isoDate(value) }
function stageLabel(value) { return String(value || 'QUEUED').replaceAll('_', ' ').toLowerCase().replace(/^./, (letter) => letter.toUpperCase()) }

export default function AdminPipelinePage({ onUnauthorized, onNavigate }) {
  useDocumentTitle('Pipeline')
  const [page, setPage] = useState(1)
  const [searchText, setSearchText] = useState('')
  const [search, setSearch] = useState('')
  const [selected, setSelected] = useState(() => new Set())
  const [fromDate, setFromDate] = useState(defaultFromDate)
  const [toDate, setToDate] = useState(() => isoDate(new Date()))
  const [forceRefresh, setForceRefresh] = useState(false)
  const [batchSize, setBatchSize] = useState(25)
  const [timeframes, setTimeframes] = useState(() => new Set(TIMEFRAMES))
  const [activeRun, setActiveRun] = useState(null)
  const [itemPage, setItemPage] = useState(1)
  const [actionError, setActionError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [controlling, setControlling] = useState('')
  const equityKey = new URLSearchParams({ page: String(page), pageSize: '25', ...(search ? { search } : {}) }).toString()
  const equities = useApiResource(equityKey, (signal) => getAdminEquities({ page, pageSize: 25, search }, { signal, onUnauthorized }))
  const recent = useApiResource('admin-pipeline-runs', (signal) => getPipelineRuns({ page: 1, pageSize: 8 }, { signal, onUnauthorized }))
  const pageIsins = useMemo(() => (equities.data?.items || []).map((item) => item.isin), [equities.data])
  const allPageSelected = pageIsins.length > 0 && pageIsins.every((isin) => selected.has(isin))
  const running = activeRun && !TERMINAL.has(activeRun.status)

  useEffect(() => {
    if (!running) return undefined
    const poll = window.setInterval(() => {
      getPipelineRun(activeRun.runId, { itemPage, itemPageSize: 25 }, { onUnauthorized })
        .then((payload) => setActiveRun(payload.run))
        .catch((error) => setActionError(error.message))
    }, 2000)
    return () => window.clearInterval(poll)
  }, [activeRun?.runId, running, itemPage, onUnauthorized])

  useEffect(() => { if (activeRun && TERMINAL.has(activeRun.status)) recent.reload() }, [activeRun?.status])

  const toggle = (isin) => setSelected((current) => {
    const next = new Set(current)
    if (next.has(isin)) next.delete(isin); else if (next.size < 100) next.add(isin)
    return next
  })
  const togglePage = () => setSelected((current) => {
    const next = new Set(current)
    if (allPageSelected) pageIsins.forEach((isin) => next.delete(isin))
    else pageIsins.forEach((isin) => { if (next.size < 100) next.add(isin) })
    return next
  })
  const applySearch = (event) => { event.preventDefault(); setPage(1); setSearch(searchText.trim()) }
  const startRun = async (runAll = false, patternOnly = false) => {
    const action = patternOnly ? `patterns-${runAll ? 'all' : 'selection'}` : runAll ? 'all' : 'selection'
    setSubmitting(action); setActionError('')
    try {
      const createRun = patternOnly ? createPatternScan : createPipelineRun
      const payload = await createRun({
        ...(runAll ? { allEquities: true } : { isins: [...selected] }),
        fromDate, toDate, forceRefresh, batchSize: Number(batchSize),
        ...(patternOnly ? { timeframes: [...timeframes] } : {}),
      }, { onUnauthorized })
      setActiveRun(payload.run)
      setItemPage(1)
      setSelected(new Set())
      recent.reload()
    } catch (error) { setActionError(error.message) }
    finally { setSubmitting(false) }
  }
  const openRun = async (runId) => {
    setActionError('')
    setItemPage(1)
    try { setActiveRun((await getPipelineRun(runId, { itemPage: 1, itemPageSize: 25 }, { onUnauthorized })).run) }
    catch (error) { setActionError(error.message) }
  }
  const toggleTimeframe = (value) => setTimeframes((current) => {
    const next = new Set(current)
    if (next.has(value) && next.size > 1) next.delete(value)
    else next.add(value)
    return next
  })

  const changeItemPage = async (nextPage) => {
    if (!activeRun) return
    setActionError('')
    try {
      const payload = await getPipelineRun(activeRun.runId, { itemPage: nextPage, itemPageSize: 25 }, { onUnauthorized })
      setItemPage(nextPage)
      setActiveRun(payload.run)
    } catch (error) { setActionError(error.message) }
  }

  const controlRun = async (action) => {
    if (!activeRun) return
    setControlling(action); setActionError('')
    try {
      const payload = await controlPipelineRun(activeRun.runId, action, { onUnauthorized })
      setActiveRun(payload.run)
      recent.reload()
    } catch (error) { setActionError(error.message) }
    finally { setControlling('') }
  }

  return <>
    <PageIntro eyebrow="Data operations" title="Market data updates" description="Update stock history and pattern analysis, then follow each run from start to finish." />
    <section className="admin-run-controls" aria-labelledby="pipeline-controls-title">
      <div><h2 id="pipeline-controls-title">{selected.size} equities selected</h2></div>
      <label>Analysis history from<input type="date" value={fromDate} max={toDate} onChange={(event) => setFromDate(event.target.value)} /></label>
      <label>Through<input type="date" value={toDate} min={fromDate} onChange={(event) => setToDate(event.target.value)} /></label>
      <label>Batch size<input type="number" min="1" max="100" value={batchSize} onChange={(event) => setBatchSize(event.target.value)} /></label>
      <label className="admin-force"><input type="checkbox" checked={forceRefresh} onChange={(event) => setForceRefresh(event.target.checked)} /><span><strong>Force source refresh</strong><small>Re-download existing ranges instead of filling gaps only.</small></span></label>
      <fieldset className='admin-timeframes'><legend>Pattern discovery intervals</legend>{TIMEFRAMES.map((value) => <label key={value}><input type='checkbox' checked={timeframes.has(value)} onChange={() => toggleTimeframe(value)} /><span>{value === '1D' ? 'Daily' : value === '1W' ? 'Weekly' : 'Monthly'}</span></label>)}</fieldset>
      <p className="admin-incremental-note"><strong>Incremental by default.</strong> With Force source refresh off, stored history is retained and only missing sessions after each equity's latest bar are requested from NSE.</p>
      <div className="admin-run-actions">
        <button className="primary-button" type="button" disabled={!selected.size || submitting || running} onClick={() => startRun(false)}>{submitting === 'selection' ? 'Queuing…' : running ? 'Run in progress' : 'Run selected'}</button>
        <button className="secondary-button" type="button" disabled={!equities.data?.totalItems || submitting || running} onClick={() => startRun(true)}>{submitting === 'all' ? 'Queuing all…' : 'Run all equities'}</button>
        <button className='secondary-button' type='button' disabled={!selected.size || submitting || running} onClick={() => startRun(false, true)}>{submitting === 'patterns-selection' ? 'Queuing…' : 'Patterns · selected'}</button>
        <button className='secondary-button' type='button' disabled={!equities.data?.totalItems || submitting || running} onClick={() => startRun(true, true)}>{submitting === 'patterns-all' ? 'Queuing all…' : 'Patterns · all'}</button>
      </div>
    </section>
    {actionError && <p className="form-message error" role="alert">{actionError}</p>}

    {activeRun && <PipelineRunStatus run={activeRun} controlling={controlling} onControl={controlRun} onNavigate={onNavigate} onItemPage={changeItemPage} />}

    <div className="admin-workspace">
      <section aria-labelledby="equity-grid-title">
        <div className="section-heading"><div><p className="eyebrow">Equity universe</p><h2 id="equity-grid-title">Select securities</h2></div><span className="date-chip"><strong>{equities.data?.totalItems || 0}</strong> equities</span></div>
        <form className="admin-search" onSubmit={applySearch} role="search">
          <label htmlFor="equity-search">Search symbol, company, or ISIN</label>
          <div><input id="equity-search" value={searchText} onChange={(event) => setSearchText(event.target.value)} placeholder="RELIANCE" /><button className="secondary-button" type="submit">Search</button></div>
        </form>
        <ResourceState status={equities.status} error={equities.error} onRetry={equities.reload}>
          {equities.data && <>
            <div className="admin-table-wrap">
              <table className="admin-equity-table">
                <thead><tr><th scope="col"><input type="checkbox" aria-label="Select every equity on this page" checked={allPageSelected} onChange={togglePage} /></th><th scope="col">Symbol</th><th scope="col">Company</th><th scope="col">Classification</th><th scope="col">ISIN</th><th scope="col">Latest data</th><th scope="col">Last pipeline</th></tr></thead>
                <tbody>{equities.data.items.length === 0 && <tr><td className="admin-table-empty" colSpan="7">No equities match this search. Import the NSE equity master if the system has not been populated yet.</td></tr>}{equities.data.items.map((equity) => <tr key={equity.isin} className={selected.has(equity.isin) ? 'is-selected' : ''}>
                  <td><input type="checkbox" aria-label={`Select ${equity.symbol}`} checked={selected.has(equity.isin)} onChange={() => toggle(equity.isin)} /></td>
                  <th scope="row">{equity.symbol}</th><td>{equity.companyName}</td><td><strong>{equity.sectorName || 'Not classified'}</strong><small>{equity.basicIndustryName || equity.classificationStatus}</small></td><td><code>{equity.isin}</code></td><td>{formatMarketDate(equity.latestRawDate)}</td><td>{equity.lastPipelineStatus || 'Never run'}</td>
                </tr>)}</tbody>
              </table>
            </div>
            <div className="pagination"><button className="secondary-button" type="button" disabled={page <= 1} onClick={() => setPage((value) => value - 1)}>Previous</button><span>Page {equities.data.page} of {Math.max(1, equities.data.totalPages)}</span><button className="secondary-button" type="button" disabled={page >= equities.data.totalPages} onClick={() => setPage((value) => value + 1)}>Next</button></div>
          </>}
        </ResourceState>
      </section>

      <aside className="admin-recent" aria-labelledby="recent-runs-title">
        <div className="section-heading"><div><p className="eyebrow">Audit trail</p><h2 id="recent-runs-title">Recent runs</h2></div></div>
        <ResourceState status={recent.status} error={recent.error} onRetry={recent.reload}>
          <div className="admin-run-list">{(recent.data?.items || []).length ? recent.data.items.map((run) => <button type="button" key={run.runId} onClick={() => openRun(run.runId)}><span><strong>{run.status}</strong><small>{run.runKind === 'PATTERN_DISCOVERY' ? 'Pattern discovery' : 'Full pipeline'} · {formatMarketDate(run.createdAt?.slice(0, 10))}</small></span><span>{run.securitiesCompleted}/{run.securitiesTotal}</span></button>) : <p className="muted-copy">No pipeline runs yet.</p>}</div>
        </ResourceState>
      </aside>
    </div>
  </>
}

function PipelineRunStatus({ run, controlling, onControl, onNavigate, onItemPage }) {
  const handled = Number(run.securitiesCompleted || 0) + Number(run.securitiesFailed || 0)
  const prepared = Number(run.securitiesPrepared || 0)
  const visiblePrepared = (run.items || []).filter((item) => item.currentStage === 'SECTOR_CONTEXT').length
  const progress = run.securitiesTotal ? ((handled * 2) + prepared) / (run.securitiesTotal * 2) * 100 : 0
  const canPause = ['PENDING', 'RUNNING'].includes(run.status)
  const canResume = ['FAILED', 'PARTIAL', 'PAUSED'].includes(run.status) && handled < Number(run.securitiesTotal || 0)
  const canTerminate = ['PENDING', 'RUNNING', 'PAUSED'].includes(run.status)
  return <section className="admin-run-status" aria-live="polite" aria-labelledby="active-run-title">
    <div className="card-title"><div><p className="eyebrow">{run.runScope === 'ALL' ? `All equities · batches of ${run.batchSize}` : 'Selected equities'}</p><h2 id="active-run-title">Run {String(run.runId).slice(0, 8)}</h2></div><StateBadge state={run.status} /></div>
    {run.status === 'RUNNING' && handled === 0 && (prepared > 0 || visiblePrepared > 0) && <p className="pipeline-phase-note"><strong>Phase 1 of 2 · Preparing the universe.</strong> {prepared > 0 ? `${prepared} equities are ready for sector context.` : `${visiblePrepared} equities on this page are ready for sector context.`} Pattern scanning starts after preparation finishes so every equity uses the same complete sector snapshot.</p>}
    {run.status === 'RUNNING' && Number(run.securitiesCompleted || 0) > 0 && <p className="pipeline-phase-note"><strong>Phase 2 of 2 · Scanning patterns.</strong> Sector context is ready and prepared equities are now being classified.</p>}
    <div className="admin-progress" aria-label={`${Math.round(progress)} percent complete`}><span style={{ width: `${progress}%` }} /></div>
    <div className="admin-run-metrics"><span>Total<strong>{run.securitiesTotal}</strong></span><span>{prepared > 0 ? 'Prepared' : 'Prepared on page'}<strong>{prepared || visiblePrepared}</strong></span><span>Completed<strong>{run.securitiesCompleted}</strong></span><span>Failed<strong>{run.securitiesFailed}</strong></span><span>Range<strong>{formatMarketDate(run.fromDate)} – {formatMarketDate(run.toDate)}</strong></span></div>
    <div className="admin-run-actions" aria-label="Pipeline run controls">
      {canPause && <button className="secondary-button" type="button" disabled={Boolean(controlling)} onClick={() => onControl('pause')}>{controlling === 'pause' ? 'Pausing…' : 'Pause after current equity'}</button>}
      {canResume && <button className="primary-button" type="button" disabled={Boolean(controlling)} onClick={() => onControl('resume')}>{controlling === 'resume' ? 'Resuming…' : 'Resume unfinished equities'}</button>}
      {canTerminate && <button className="secondary-button" type="button" disabled={Boolean(controlling)} onClick={() => onControl('terminate')}>{controlling === 'terminate' ? 'Terminating…' : 'Terminate run'}</button>}
    </div>
    {run.errorSummary && <p className="form-message error">{run.errorSummary}</p>}
    <div className="admin-item-grid">{(run.items || []).map((item) => { const preparedItem = item.currentStage === 'SECTOR_CONTEXT'; return <article key={item.isin}><div><strong>{item.symbol}</strong><small>{item.isin}</small></div><StateBadge state={preparedItem ? 'PREPARED' : item.status} /><p>{preparedItem ? 'Waiting for universe sector context' : stageLabel(item.currentStage)}</p><dl><div><dt>Rows</dt><dd>{item.rowsDownloaded || 0}</dd></div><div><dt>Candidates</dt><dd>{item.candidatesDetected || 0}</dd></div></dl>{item.error && <small className="admin-item-error">{item.error}</small>}{item.status === 'COMPLETED' && item.symbol && <button type="button" className="text-button" onClick={() => onNavigate(buildSecurityPath(item.symbol))}>Inspect evidence -&gt;</button>}</article> })}</div>
    {Number(run.itemTotalPages || 0) > 1 && <div className="pagination admin-item-pagination"><button className="secondary-button" type="button" disabled={run.itemPage <= 1} onClick={() => onItemPage(run.itemPage - 1)}>Previous items</button><span>Items page {run.itemPage} of {run.itemTotalPages}</span><button className="secondary-button" type="button" disabled={run.itemPage >= run.itemTotalPages} onClick={() => onItemPage(run.itemPage + 1)}>Next items</button></div>}
  </section>
}

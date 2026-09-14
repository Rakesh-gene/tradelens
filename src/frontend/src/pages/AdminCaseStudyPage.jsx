import React, { useEffect, useState } from 'react'
import { createCaseStudyRun, getCaseStudyReviewQueue, getCaseStudyRun, getCaseStudyRunItems, resumeCaseStudyRun, reviewCaseStudy } from '../api/adminApi.js'
import CaseStudyStockPicker from '../components/CaseStudyStockPicker.jsx'
import { PageIntro, StateBadge } from '../components/PatternUi.jsx'
import { buildCaseStudyPath } from '../routing/routes.js'
import { formatMarketDate, formatPercent } from '../utils/formatters.js'

const terminal = new Set(['COMPLETED', 'PARTIAL', 'FAILED'])
const ranges = [['3M', '3 months'], ['6M', '6 months'], ['1Y', '1 year'], ['3Y', '3 years'], ['5Y', '5 years']]

export default function AdminCaseStudyPage({ onNavigate, onUnauthorized }) {
  const [stock, setStock] = useState(null)
  const [lookback, setLookback] = useState('1Y')
  const [run, setRun] = useState(null)
  const [items, setItems] = useState([])
  const [reviewQueue, setReviewQueue] = useState([])
  const [publishing, setPublishing] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (!run || terminal.has(run.status)) return undefined
    const timer = window.setInterval(async () => {
      try {
        const [status, progress] = await Promise.all([getCaseStudyRun(run.runId, { onUnauthorized }), getCaseStudyRunItems(run.runId, { pageSize: 100 }, { onUnauthorized })])
        setRun(status.run); setItems(progress.items)
      } catch (reason) { setError(reason.message) }
    }, 2000)
    return () => window.clearInterval(timer)
  }, [run?.runId, run?.status, onUnauthorized])

  useEffect(() => {
    if (run && !terminal.has(run.status)) return undefined
    const controller = new AbortController()
    getCaseStudyReviewQueue({ status: 'PENDING', pageSize: 100 }, { signal: controller.signal, onUnauthorized })
      .then((response) => setReviewQueue(response.items || []))
      .catch((reason) => { if (reason.name !== 'AbortError') setError(reason.message) })
    return () => controller.abort()
  }, [run?.status, onUnauthorized])

  const start = async (event) => {
    event.preventDefault(); setError('')
    if (!stock) { setError('Select a stock from the search results.'); return }
    setBusy(true)
    try {
      const response = await createCaseStudyRun({ isin: stock.isin, lookback }, { onUnauthorized })
      setRun(response.run); setItems([])
    } catch (reason) { setError(reason.message) } finally { setBusy(false) }
  }
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

  return <section className="page-stack">
    <PageIntro eyebrow="Case study builder" title="Build a stock case study" description="Choose a stock and time period to create historical cases you can inspect and publish." />
    <form className="evidence-card case-study-build-form" onSubmit={start}>
      <CaseStudyStockPicker value={stock} onChange={setStock} onUnauthorized={onUnauthorized} />
      <label>Date range<select className="select-control" value={lookback} onChange={(event) => setLookback(event.target.value)}>{ranges.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
      <div className="filter-actions"><button className="primary-button" disabled={busy} type="submit">{busy ? 'Starting…' : 'Build case study'}</button></div>
    </form>
    {error && <p className="form-message error" role="alert">{error}</p>}
    {run && <section className="evidence-card" aria-live="polite">
      <div className="card-title"><div><p className="eyebrow">Build run {run.runId.slice(0, 8)}</p><h2>{run.stock?.symbol || run.stock?.isin || 'Selected stock'}</h2></div><StateBadge state={run.status} /></div>
      <p>{run.casesRecorded} case studies recorded for {run.lookback || lookback} ({formatMarketDate(run.fromDate)} – {formatMarketDate(run.toDate)}).</p>
      {run.status === 'COMPLETED' && !run.caseStudyIds?.length && <p>No triggered or confirmed patterns were found for this stock in the selected range.</p>}
      {!!run.caseStudyIds?.length && <div className="case-study-id-list"><h3>Generated case IDs</h3>{run.caseStudyIds.map((id) => <button className="secondary-button" type="button" key={id} onClick={() => onNavigate(buildCaseStudyPath(id))}>{id}</button>)}</div>}
      {['FAILED', 'PARTIAL'].includes(run.status) && <button className="secondary-button" type="button" disabled={busy} onClick={resume}>Resume build</button>}
      <div className="admin-item-grid">{items.map((item) => <article key={item.isin}><strong>{item.isin}</strong><StateBadge state={item.status} /><p>{item.casesRecorded} cases</p>{item.errorMessage && <small className="admin-item-error">{item.errorMessage}</small>}</article>)}</div>
    </section>}
    <section className="evidence-card case-study-review-queue">
      <div className="card-title"><div><p className="eyebrow">Publication gate</p><h2>Cases awaiting review</h2></div><span className="metric-pill">{reviewQueue.length}</span></div>
      <p>Inspect the chart, entry rationale, and forward stock performance first. Publishing moves the case into the Case Studies catalog.</p>
      {reviewQueue.length === 0 ? <p className="muted-copy">No case studies are awaiting review.</p> : <div className="admin-item-grid">{reviewQueue.map((item) => <article key={item.caseStudyId}>
        <strong>{item.symbol || item.isin}</strong><small>{item.patternType} · {item.timeframe} · {formatMarketDate(item.detectionDate)}</small><p>3M {formatPercent(item.positionalPerformance?.horizons?.['3M']?.returnPct, { signed: true })} · 6M {formatPercent(item.positionalPerformance?.horizons?.['6M']?.returnPct, { signed: true })} · 1Y {formatPercent(item.positionalPerformance?.horizons?.['1Y']?.returnPct, { signed: true })}</p>
        <div className="case-study-review-actions"><button className="secondary-button" type="button" onClick={() => onNavigate(buildCaseStudyPath(item.caseStudyId))}>Inspect</button><button className="primary-button" type="button" disabled={Boolean(publishing)} onClick={() => publish(item.caseStudyId)}>{publishing === item.caseStudyId ? 'Publishing…' : 'Publish reviewed case'}</button></div>
      </article>)}</div>}
    </section>
  </section>
}

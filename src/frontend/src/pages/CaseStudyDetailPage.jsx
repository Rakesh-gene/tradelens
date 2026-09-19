import React from 'react'
import { getCaseStudy, getCaseStudyChart } from '../api/caseStudyApi.js'
import useApiResource from '../useApiResource.js'
import { ResourceState } from '../components/ResourceStates.jsx'
import PatternCandlestickChart from '../components/PatternCandlestickChart.jsx'
import Breadcrumbs from '../components/Breadcrumbs.jsx'
import { PageIntro } from '../components/PatternUi.jsx'
import { formatMarketDate, formatPrice, formatPercent } from '../utils/formatters.js'
import { describePattern } from '../utils/patternDescriptions.js'
import { deleteCaseStudy } from '../api/adminApi.js'
import ConfirmDialog from '../components/ConfirmDialog.jsx'
import { buildSecurityPath } from '../routing/routes.js'

const horizons = ['3M', '6M', '1Y']

export default function CaseStudyDetailPage({ caseStudyId, onNavigate, onUnauthorized, isAdmin = false }) {
  const resource = useApiResource(caseStudyId, async (signal) => {
    const [detail, chart] = await Promise.all([getCaseStudy(caseStudyId, { signal, onUnauthorized }), getCaseStudyChart(caseStudyId, { signal, onUnauthorized })])
    return { ...detail, chart }
  })
  const [deleting, setDeleting] = React.useState(false)
  const [confirmingDelete, setConfirmingDelete] = React.useState(false)
  const [deleteError, setDeleteError] = React.useState('')
  const remove = async () => {
    setDeleting(true); setDeleteError('')
    try { await deleteCaseStudy(caseStudyId, { onUnauthorized }); onNavigate('/case-studies', { replace: true }) }
    catch (error) { setDeleteError(error.message || 'Could not delete this case study.') }
    finally { setDeleting(false) }
  }
  return <ResourceState status={resource.status} error={resource.error} onRetry={resource.reload}>{resource.data && (() => {
    const item = resource.data.caseStudy
    const rationale = item.entryRationale || {}
    const performance = item.positionalPerformance || {}
    const pattern = describePattern(item.patternType)
    return <section className="page-stack">
      <Breadcrumbs onNavigate={onNavigate} items={[{ label: 'Case studies', to: '/case-studies' }, { label: item.symbol, to: buildSecurityPath(item.symbol) }, { label: item.variant || item.patternType }]} />
      <PageIntro eyebrow="Historical case study" title={`${item.symbol || item.isin} · ${item.variant || item.patternType}`} description={`Detected ${formatMarketDate(item.detectionDate)}. Review the chart, what supported the entry, and how the stock moved afterward.`} />
      {isAdmin && <div className="case-study-admin-actions"><button className="case-study-delete" type="button" disabled={deleting} onClick={() => setConfirmingDelete(true)} aria-label={deleting ? 'Deleting case study' : 'Delete case study'} title={deleting ? 'Deleting case study' : 'Delete case study'}><svg aria-hidden="true" viewBox="0 0 24 24" fill="none"><path d="M4 7h16M9.5 11v5M14.5 11v5M9 7l.7-2h4.6l.7 2M6.5 7l.7 12h10.6l.7-12" /></svg></button></div>}
      {deleteError && <p className="form-message error" role="alert">{deleteError}</p>}

      <section className="evidence-card case-study-chart"><PatternCandlestickChart candles={resource.data.chart.candles} levels={resource.data.chart.levels} milestones={resource.data.chart.milestones} selectedPatternId={caseStudyId} evidence={resource.data.chart.evidence} /><details><summary>Open the complete adjusted-price table ({resource.data.chart.candles.length} sessions)</summary><div className="table-scroll"><table><caption>Adjusted prices used for the positional case study</caption><thead><tr><th>Date</th><th>Open</th><th>High</th><th>Low</th><th>Close</th></tr></thead><tbody>{resource.data.chart.candles.map((bar) => <tr key={bar.date}><td>{formatMarketDate(bar.date)}</td><td>{formatPrice(bar.open)}</td><td>{formatPrice(bar.high)}</td><td>{formatPrice(bar.low)}</td><td>{formatPrice(bar.close)}</td></tr>)}</tbody></table></div></details></section>

      <section className="evidence-card pattern-explanation"><p className="eyebrow">Pattern guide</p><h2>What is a {pattern.label}?</h2><p>{pattern.description}</p><p>{pattern.confirmation}</p></section>

      <section className="evidence-card"><p className="eyebrow">Reason to enter</p><h2>What qualified at the time</h2><p className="case-study-thesis">{rationale.summary}</p><dl className="level-grid"><div><dt>Entry anchor</dt><dd>{formatMarketDate(performance.entryDate || item.entryDate)} · {formatPrice(performance.entryPrice || item.entryPrice)}</dd></div><div><dt>Reference pivot</dt><dd>{formatPrice(item.prices?.pivotPrice)}</dd></div><div><dt>Support</dt><dd>{formatPrice(item.prices?.supportPrice)}</dd></div><div><dt>Invalidation</dt><dd>{formatPrice(item.prices?.invalidationPrice)}</dd></div></dl><ul className="case-study-reasons">{rationale.reasons?.map((reason) => <li key={reason}>{reason}</li>)}</ul><p className="status-note">{rationale.entryRule}</p>{rationale.cautions?.map((caution) => <p className="muted-copy" key={caution}>Caution: {caution}</p>)}</section>

      <section className="evidence-card"><p className="eyebrow">Forward performance</p><h2>How the stock performed after entry</h2><p>Returns compare each horizon’s adjusted close with the next-session adjusted opening price. Three, six, and twelve months use 63, 126, and 252 trading sessions.</p><ToDatePerformance value={performance.performanceToDate} /><div className="positional-performance-grid">{horizons.map((key) => <PerformanceCard key={key} name={key} value={performance.horizons?.[key]} />)}</div></section>

      <section className="lineage"><span>Data as of {formatMarketDate(resource.data.dataAsOf)}</span><span>Engine {item.lineage?.engineVersion || '—'}</span><span>Configuration {item.lineage?.configurationVersion || '—'}</span><span>Features {item.lineage?.featureVersion || '—'}</span><span>Adjustments {item.lineage?.adjustmentVersion || '—'}</span></section>
      <ConfirmDialog open={confirmingDelete} title="Delete this case study?" message="This permanently removes the case study and its recorded performance. This cannot be undone." busy={deleting} onCancel={() => setConfirmingDelete(false)} onConfirm={remove} />
    </section>
  })()}</ResourceState>
}

function PerformanceCard({ name, value = {} }) {
  return <article className="positional-performance-card"><div><span>{name}</span><strong>{value.complete ? formatPercent(value.returnPct, { signed: true }) : 'Pending'}</strong></div><dl><div><dt>Observed</dt><dd>{formatMarketDate(value.observationDate)}</dd></div><div><dt>Adjusted close</dt><dd>{formatPrice(value.closePrice)}</dd></div><div><dt>Maximum advance</dt><dd>{formatPercent(value.maxAdvancePct, { signed: true })}</dd></div><div><dt>Maximum drawdown</dt><dd>{formatPercent(value.maxDrawdownPct, { signed: true })}</dd></div></dl><small>{value.complete ? `${value.targetSessions} trading sessions complete` : `${value.availableSessions || 0} of ${value.targetSessions || 0} sessions available`}</small></article>
}

function ToDatePerformance({ value = {} }) {
  if (!value.observationDate) return null
  return <div className="positional-to-date"><span>Performance so far</span><strong>{formatPercent(value.returnPct, { signed: true })}</strong><small>Through {formatMarketDate(value.observationDate)} · {value.availableSessions} trading sessions · adjusted close {formatPrice(value.closePrice)}</small></div>
}

import { formatMarketDate } from '../utils/formatters.js'

export default function DataFreshness({ dataAsOf, generatedAt, isStale, pipeline }) {
  return <>
    {isStale && <div className="status-banner" role="status">This is end-of-day data from {formatMarketDate(dataAsOf)}. Confirm the latest completed scan before acting.</div>}
    <section className="freshness-card" aria-label="Data freshness">
      <div><span>Data as of</span><strong>{formatMarketDate(dataAsOf)}</strong></div>
      <div><span>Pipeline</span><strong>{pipeline?.status || 'Unavailable'}</strong></div>
      <div><span>Securities scanned</span><strong>{pipeline?.securitiesScanned ?? '—'}</strong></div>
      <div><span>Generated</span><strong>{generatedAt ? new Intl.DateTimeFormat('en-IN', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(generatedAt)) : 'Unavailable'}</strong></div>
    </section>
  </>
}

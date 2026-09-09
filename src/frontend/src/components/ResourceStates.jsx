export function LoadingSkeleton({ label = 'Loading market evidence…' }) {
  return <section className="loading-panel" aria-busy="true" aria-label={label}><div /><div /><div /><p>{label}</p></section>
}

export function EmptyState({ title, message, action }) {
  return <section className="empty-panel"><h2>{title}</h2><p>{message}</p>{action}</section>
}

export function ErrorState({ error, onRetry }) {
  const status = error?.status
  const title = status === 403 ? 'Access restricted' : status === 404 ? 'Resource not found' : status === 429 ? 'Too many requests' : 'Data unavailable'
  return <section className="empty-panel" role="alert"><h2>{title}</h2><p>{error?.message || 'TradeLens could not load this data.'}</p>{onRetry && status !== 403 && status !== 404 && <button className="secondary-button" type="button" onClick={onRetry}>Try again</button>}</section>
}

export function ResourceState({ status, error, onRetry, children }) {
  if (status === 'loading') return <LoadingSkeleton />
  if (status === 'error') return <ErrorState error={error} onRetry={onRetry} />
  return <>{status === 'refreshing' && <p className="refresh-status" role="status">Refreshing evidence…</p>}{children}</>
}

import { useMemo, useState } from 'react'
import useApiResource from '../useApiResource.js'
import { addToWatchlist, getWatchlist, removeFromWatchlist } from '../api/watchlistApi.js'

export default function WatchlistButton({ isin, onUnauthorized }) {
  const resource = useApiResource(`watchlist:${isin}`, (signal) => getWatchlist({ signal, onUnauthorized }))
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const watched = useMemo(
    () => resource.data?.items?.some((item) => item.security.isin === isin) || false,
    [resource.data, isin],
  )
  const toggle = async () => {
    setSaving(true)
    setError('')
    try {
      if (watched) await removeFromWatchlist(isin, { onUnauthorized })
      else await addToWatchlist(isin, { onUnauthorized })
      resource.reload()
    } catch (requestError) {
      setError(requestError.message || 'Could not update your watchlist.')
    } finally {
      setSaving(false)
    }
  }
  return <div className="watchlist-action">
    <button className={watched ? 'secondary-button' : 'primary-button'} type="button" disabled={saving || resource.status === 'loading'} onClick={toggle} aria-pressed={watched}>
      {saving ? 'Saving…' : watched ? 'Remove from watchlist' : 'Add to watchlist'}
    </button>
    {error && <p className="form-error" role="alert">{error}</p>}
  </div>
}

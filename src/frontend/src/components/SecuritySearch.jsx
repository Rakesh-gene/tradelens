import { useEffect, useId, useRef, useState } from 'react'
import { searchSecurities } from '../api/securityApi.js'
import { addToWatchlist, getWatchlist } from '../api/watchlistApi.js'
import { buildSecurityPath } from '../routing/routes.js'

export default function SecuritySearch({ onNavigate, onUnauthorized, onWatchlistChanged }) {
  const listId = useId()
  const input = useRef(null)
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [activeIndex, setActiveIndex] = useState(-1)
  const [status, setStatus] = useState('idle')
  const [message, setMessage] = useState('')
  const [watchlisted, setWatchlisted] = useState(() => new Set())
  const [adding, setAdding] = useState('')
  const [watchlistMessage, setWatchlistMessage] = useState('')
  const choose = (security) => {
    setQuery(''); setResults([]); setActiveIndex(-1); setMessage('')
    onNavigate(buildSecurityPath(security.symbol))
  }
  useEffect(() => {
    const controller = new AbortController()
    getWatchlist({ signal: controller.signal, onUnauthorized })
      .then((payload) => setWatchlisted(new Set((payload.items || []).map((item) => item.security.isin))))
      .catch((error) => { if (error.name !== 'AbortError') setWatchlistMessage('Watchlist status is temporarily unavailable.') })
    return () => controller.abort()
  }, [onUnauthorized])
  const add = async (security) => {
    setAdding(security.isin)
    setWatchlistMessage('')
    try {
      const result = await addToWatchlist(security.isin, { onUnauthorized })
      setWatchlisted((current) => new Set([...current, security.isin]))
      setWatchlistMessage(`${security.symbol || security.name} added to your watchlist.`)
      if (result.added) onWatchlistChanged?.({ action: 'added', isin: security.isin })
    } catch (error) {
      setWatchlistMessage(error.message || 'Could not add this stock to your watchlist.')
    } finally {
      setAdding('')
    }
  }
  useEffect(() => {
    const value = query.trim()
    if (value.length < 2) { setResults([]); setActiveIndex(-1); setStatus('idle'); setMessage(''); return undefined }
    const controller = new AbortController()
    const timer = window.setTimeout(async () => {
      setStatus('loading'); setMessage('')
      try {
        const payload = await searchSecurities({ q: value, limit: 20 }, { signal: controller.signal, onUnauthorized })
        const items = payload.items || []
        setResults(items); setActiveIndex(items.length ? 0 : -1); setMessage(items.length ? `${items.length} matching equities.` : `No equity starts with “${value}”.`); setStatus('success')
      } catch (error) {
        if (error.name !== 'AbortError') { setResults([]); setMessage(error.message); setStatus('error') }
      }
    }, 250)
    return () => { window.clearTimeout(timer); controller.abort() }
  }, [query, onUnauthorized])
  const keyDown = (event) => {
    if (event.key === 'ArrowDown' && results.length) { event.preventDefault(); setActiveIndex((value) => (value + 1) % results.length) }
    else if (event.key === 'ArrowUp' && results.length) { event.preventDefault(); setActiveIndex((value) => (value - 1 + results.length) % results.length) }
    else if (event.key === 'Enter' && activeIndex >= 0) { event.preventDefault(); choose(results[activeIndex]) }
    else if (event.key === 'Escape') { setResults([]); setActiveIndex(-1); setMessage(''); input.current?.focus() }
  }
  return <div className="security-jump"><label htmlFor={`${listId}-input`}>Search equities by name or symbol</label><div className="security-search-control"><svg className="security-search-icon" aria-hidden="true" viewBox="0 0 24 24" fill="none"><circle cx="11" cy="11" r="6.5" /><path d="m16 16 4 4" /></svg><input ref={input} id={`${listId}-input`} role="combobox" aria-autocomplete="list" aria-controls={listId} aria-expanded={results.length > 0} aria-activedescendant={activeIndex >= 0 ? `${listId}-${activeIndex}` : undefined} value={query} onChange={(event) => setQuery(event.target.value)} onKeyDown={keyDown} placeholder="Search by company or symbol" autoComplete="off" /><span className="security-search-hint" aria-hidden="true">Equities</span></div>{(status === 'loading' || results.length > 0 || message) && <div id={listId} className="security-search-popover" role="listbox" aria-label="Matching equities">{status === 'loading' && <p>Searching equities…</p>}{results.map((security, index) => { const saved = watchlisted.has(security.isin); return <div className="security-search-result" key={security.isin}><button className="security-result-button" id={`${listId}-${index}`} type="button" role="option" aria-selected={index === activeIndex} onMouseEnter={() => setActiveIndex(index)} onClick={() => choose(security)}><strong>{security.symbol}</strong><span>{security.name}</span>{security.sectorName && <small>{security.sectorName}</small>}</button><button className="watchlist-search-button" type="button" disabled={saved || adding === security.isin} onClick={() => add(security)} aria-label={`${saved ? 'In watchlist' : 'Add to watchlist'}: ${security.symbol || security.name}`}><span aria-hidden="true">{saved ? '✓' : '+'}</span>{adding === security.isin ? 'Adding…' : saved ? 'Saved' : 'Add'}</button></div> })}{message && status !== 'loading' && <p className="visually-hidden" role="status">{message}</p>}{watchlistMessage && <p className="security-search-message" role="status">{watchlistMessage}</p>}{status === 'error' && <p>{message}</p>}</div>}</div>
}

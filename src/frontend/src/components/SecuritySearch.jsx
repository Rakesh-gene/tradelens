import { useEffect, useId, useRef, useState } from 'react'
import { searchSecurities } from '../api/securityApi.js'
import { buildSecurityPath } from '../routing/routes.js'

export default function SecuritySearch({ onNavigate, onUnauthorized }) {
  const listId = useId()
  const input = useRef(null)
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [activeIndex, setActiveIndex] = useState(-1)
  const [status, setStatus] = useState('idle')
  const [message, setMessage] = useState('')
  const choose = (security) => {
    setQuery(''); setResults([]); setActiveIndex(-1); setMessage('')
    onNavigate(buildSecurityPath(security.isin))
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
  return <div className="security-jump"><label htmlFor={`${listId}-input`}>Search equities by name or symbol</label><div className="security-search-control"><input ref={input} id={`${listId}-input`} role="combobox" aria-autocomplete="list" aria-controls={listId} aria-expanded={results.length > 0} aria-activedescendant={activeIndex >= 0 ? `${listId}-${activeIndex}` : undefined} value={query} onChange={(event) => setQuery(event.target.value)} onKeyDown={keyDown} placeholder="Reliance or RELIANCE" autoComplete="off" /><span aria-hidden="true">⌕</span></div>{(status === 'loading' || results.length > 0 || message) && <div id={listId} className="security-search-popover" role="listbox" aria-label="Matching equities">{status === 'loading' && <p>Searching equities…</p>}{results.map((security, index) => <button id={`${listId}-${index}`} type="button" role="option" aria-selected={index === activeIndex} key={security.isin} onMouseEnter={() => setActiveIndex(index)} onClick={() => choose(security)}><strong>{security.symbol}</strong><span>{security.name}</span><small>{security.sectorName || security.isin}</small></button>)}{message && status !== 'loading' && <p className="visually-hidden" role="status">{message}</p>}{status === 'error' && <p>{message}</p>}</div>}</div>
}

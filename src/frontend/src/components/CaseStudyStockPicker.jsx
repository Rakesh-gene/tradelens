import { useEffect, useId, useRef, useState } from 'react'
import { searchSecurities } from '../api/securityApi.js'

export default function CaseStudyStockPicker({ value, onChange, onUnauthorized }) {
  const listId = useId()
  const inputRef = useRef(null)
  const [query, setQuery] = useState(value ? stockLabel(value) : '')
  const [results, setResults] = useState([])
  const [activeIndex, setActiveIndex] = useState(-1)
  const [status, setStatus] = useState('idle')
  const [message, setMessage] = useState('')

  useEffect(() => {
    if (value && query === stockLabel(value)) return undefined
    const term = query.trim()
    if (term.length < 2) { setResults([]); setActiveIndex(-1); setStatus('idle'); setMessage(''); return undefined }
    const controller = new AbortController()
    const timer = window.setTimeout(async () => {
      setStatus('loading'); setMessage('')
      try {
        const payload = await searchSecurities({ q: term, limit: 12 }, { signal: controller.signal, onUnauthorized })
        const items = payload.items || []
        setResults(items); setActiveIndex(items.length ? 0 : -1); setStatus('success')
        setMessage(items.length ? `${items.length} matching stocks.` : `No stocks found for “${term}”.`)
      } catch (error) {
        if (error.name !== 'AbortError') { setResults([]); setActiveIndex(-1); setStatus('error'); setMessage(error.message) }
      }
    }, 250)
    return () => { window.clearTimeout(timer); controller.abort() }
  }, [query, value, onUnauthorized])

  const choose = (security) => { onChange(security); setQuery(stockLabel(security)); setResults([]); setActiveIndex(-1); setMessage(''); inputRef.current?.focus() }
  const changeQuery = (event) => { if (value) onChange(null); setQuery(event.target.value) }
  const keyDown = (event) => {
    if (event.key === 'ArrowDown' && results.length) { event.preventDefault(); setActiveIndex((current) => (current + 1) % results.length) }
    else if (event.key === 'ArrowUp' && results.length) { event.preventDefault(); setActiveIndex((current) => (current - 1 + results.length) % results.length) }
    else if (event.key === 'Enter' && activeIndex >= 0) { event.preventDefault(); choose(results[activeIndex]) }
    else if (event.key === 'Escape') { setResults([]); setActiveIndex(-1); inputRef.current?.focus() }
  }

  return <div className="case-study-stock-picker">
    <label htmlFor={`${listId}-input`}>Stock</label>
    <input ref={inputRef} id={`${listId}-input`} role="combobox" aria-autocomplete="list" aria-controls={listId} aria-expanded={results.length > 0} aria-activedescendant={activeIndex >= 0 ? `${listId}-${activeIndex}` : undefined} autoComplete="off" placeholder="Search by stock name or symbol" value={query} onChange={changeQuery} onKeyDown={keyDown} />
    {(status === 'loading' || results.length > 0 || message) && <div id={listId} className="case-study-stock-results" role="listbox" aria-label="Matching stocks">
      {status === 'loading' && <p>Searching stocks…</p>}
      {results.map((security, index) => <button id={`${listId}-${index}`} key={security.isin} type="button" role="option" aria-selected={index === activeIndex} onMouseEnter={() => setActiveIndex(index)} onClick={() => choose(security)}><strong>{security.symbol}</strong><span>{security.name}</span><small>{security.isin}</small></button>)}
      {message && status !== 'loading' && <p role="status">{message}</p>}
    </div>}
    {value && <small className="case-study-stock-selected">Selected: {value.symbol} · {value.isin}</small>}
  </div>
}

function stockLabel(stock) { return `${stock.symbol || stock.isin} — ${stock.name || stock.isin}` }

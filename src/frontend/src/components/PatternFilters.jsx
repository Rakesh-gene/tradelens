import { useEffect, useRef } from 'react'
import { PATTERN_CLASSES, SETUP_STATES, SUPPORTED_PATTERN_TYPES } from '../utils/setupFilters.js'

export default function PatternFilters({ filters, facets, onChange, onApply, onClear, drawer = false, open = false, onClose }) {
  const panel = useRef(null)
  useEffect(() => {
    if (!drawer || !open) return undefined
    const previous = document.activeElement
    panel.current?.querySelector('select, input, button')?.focus()
    const keydown = (event) => {
      if (event.key === 'Escape') onClose()
      if (event.key === 'Tab') {
        const focusable = [...panel.current.querySelectorAll('select, input, button')]
        const first = focusable[0]
        const last = focusable.at(-1)
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus() }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
      }
    }
    document.addEventListener('keydown', keydown)
    return () => { document.removeEventListener('keydown', keydown); previous?.focus?.() }
  }, [drawer, open])
  if (drawer && !open) return null
  const change = (name) => (event) => onChange(name, event.target.value)
  const counts = new Map((facets?.patternTypes || []).map((item) => [item.value, item.count]))
  const patternTypes = SUPPORTED_PATTERN_TYPES
  const form = <form className="filter-bar" onSubmit={onApply}>
    {drawer && <div className="filter-drawer__head"><h2>Filter setups</h2><button type="button" className="secondary-button" onClick={onClose} aria-label="Close filters">Close</button></div>}
    <label>Market date<input type="date" value={filters.asOf} onChange={change('asOf')} /></label>
    <label>Lifecycle state<select value={filters.state} onChange={change('state')}><option value="">All states</option>{SETUP_STATES.map((value) => <option key={value}>{value}</option>)}</select></label>
    <label>Pattern family<select value={filters.patternClass} onChange={change('patternClass')}><option value="">All families</option>{PATTERN_CLASSES.map((value) => <option key={value}>{value}</option>)}</select></label>
    <label>Pattern type<select value={filters.patternType} onChange={change('patternType')}><option value="">All types</option>{patternTypes.map((value) => <option key={value} value={value}>{value}{counts.has(value) ? ` (${counts.get(value)})` : ''}</option>)}</select></label>
    <label>Minimum setup score<input type="number" min="0" max="100" value={filters.minSetupScore} onChange={change('minSetupScore')} /></label>
    <label>Rank by<select value={filters.sort} onChange={change('sort')}><option value="bestFit">Best fit</option><option value="setupScore">Setup score</option><option value="qualityScore">Quality</option><option value="maturityScore">Maturity</option><option value="detectedDate">Detected date</option><option value="distanceToPivotPct">Distance to pivot</option></select></label>
    <label>Direction<select value={filters.direction} onChange={change('direction')}><option value="desc">Highest first</option><option value="asc">Lowest first</option></select></label>
    <div className="filter-actions"><button className="primary-button" type="submit">Apply filters</button><button className="secondary-button" type="button" onClick={onClear}>Clear</button></div>
  </form>
  return drawer ? <div className="filter-drawer-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose() }}><section ref={panel} className="filter-drawer" role="dialog" aria-modal="true" aria-label="Setup filters">{form}</section></div> : form
}

export default function PaginationControls({ hasPrevious, hasNext, onPrevious, onNext, busy = false, label = 'Results pages' }) {
  return <nav className="pagination" aria-label={label}><button className="secondary-button" type="button" disabled={!hasPrevious || busy} onClick={onPrevious}>First page</button><button className="secondary-button" type="button" disabled={!hasNext || busy} onClick={onNext}>Next page</button></nav>
}

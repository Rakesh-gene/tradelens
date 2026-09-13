import { formatMarketDate } from '../utils/formatters.js'

export default function PatternTimeline({ events = [] }) {
  if (!events.length) return <p className="muted-copy">No lifecycle events recorded.</p>
  return <ol className="timeline">{events.map((event) => <li key={event.eventId}><span>{formatMarketDate(event.effectiveDate)}</span><strong>{event.eventType}</strong><p>{event.previousState || 'Created'} → {event.newState}</p></li>)}</ol>
}

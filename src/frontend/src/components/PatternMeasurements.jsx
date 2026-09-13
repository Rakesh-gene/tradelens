import { formatMeasurementValue, labelize, roundStructuredNumbers } from '../utils/formatters.js'

const HIDDEN_MEASUREMENTS = new Set(['quality_components'])

export default function PatternMeasurements({ patternType, values = {} }) {
  const visible = Object.entries(values).filter(([key]) => key !== 'scoring' && !HIDDEN_MEASUREMENTS.has(key))
  const scalar = visible.filter(([, value]) => value != null && typeof value !== 'object')
  const structured = visible.filter(([, value]) => value != null && typeof value === 'object')
  return <section aria-label={`${patternType || 'Pattern'} measurements`}>
    {scalar.length ? <dl className="measurement-grid">{scalar.map(([key, value]) => <div key={key}><dt>{labelize(key)}</dt><dd>{formatMeasurementValue(value)}</dd></div>)}</dl> : <p className="muted-copy">No scalar measurements are available for this detector version.</p>}
    {structured.length > 0 && <details><summary>Additional structured measurements</summary><div className="structured-measurements">{structured.map(([key, value]) => <details key={key}><summary>{labelize(key)}</summary><pre>{JSON.stringify(roundStructuredNumbers(value), null, 2)}</pre></details>)}</div></details>}
  </section>
}

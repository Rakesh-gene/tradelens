import { labelize } from '../utils/formatters.js'

export default function PatternMeasurements({ patternType, values = {} }) {
  const scalar = Object.entries(values).filter(([key, value]) => key !== 'scoring' && value != null && typeof value !== 'object')
  const structured = Object.entries(values).filter(([key, value]) => key !== 'scoring' && value != null && typeof value === 'object')
  return <section aria-label={`${patternType || 'Pattern'} measurements`}>
    {scalar.length ? <dl className="measurement-grid">{scalar.map(([key, value]) => <div key={key}><dt>{labelize(key)}</dt><dd>{typeof value === 'boolean' ? (value ? 'Yes' : 'No') : String(value)}</dd></div>)}</dl> : <p className="muted-copy">No scalar measurements are available for this detector version.</p>}
    {structured.length > 0 && <details><summary>Additional structured measurements</summary><div className="structured-measurements">{structured.map(([key, value]) => <details key={key}><summary>{labelize(key)}</summary><pre>{JSON.stringify(value, null, 2)}</pre></details>)}</div></details>}
  </section>
}

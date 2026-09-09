import { formatScore } from '../utils/formatters.js'

export function ScoreGauge({ label, value }) {
  const width = Math.max(0, Math.min(100, Number(value) || 0))
  return <div className="score"><div><span>{label}</span><strong>{formatScore(value)}</strong></div><div className="score-track" aria-hidden="true"><span style={{ width: `${width}%` }} /></div></div>
}

export default function ScoreBreakdown({ scores, components }) {
  return <section aria-label="Score breakdown">
    {Object.entries(scores || {}).map(([label, value]) => <ScoreGauge key={label} label={label} value={value} />)}
    {components && Object.keys(components).length > 0 && <details><summary>Scoring components</summary><dl className="measurement-grid">{Object.entries(components).map(([name, value]) => <div key={name}><dt>{name}</dt><dd>{String(value)}</dd></div>)}</dl></details>}
    <p className="ranking-note">Ranking score, not historical probability.</p>
  </section>
}

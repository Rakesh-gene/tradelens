import { formatPercent, formatPrice, formatScore } from '../utils/formatters.js'

export default function DecisionSummary({ decision, compact = false }) {
  if (!decision) return null
  const levels = decision.levels || {}
  return <div className={`decision-summary decision-summary--${decision.tone || 'neutral'}${compact ? ' decision-summary--compact' : ''}`}>
    <div className="decision-summary__top">
      <span className="decision-action">{decision.actionLabel}</span>
      <span className="decision-confidence">{decision.confidenceBand === 'UNAVAILABLE' ? 'Confidence unavailable' : `${decision.confidenceBand} confidence · ${formatScore(decision.confidenceScore)}`}</span>
    </div>
    <strong className="decision-headline">{decision.headline}</strong>
    {compact && decision.nextStep && <p className="decision-next">{decision.nextStep}</p>}
    {!compact && <>
      <p className="decision-summary__meaning">{decision.summary}</p>
      <p className="decision-next"><span>Next step</span>{decision.nextStep}</p>
      {(levels.triggerPrice != null || levels.invalidationPrice != null) && <dl className="decision-levels">
        {levels.triggerPrice != null && <div><dt>Trigger</dt><dd>{formatPrice(levels.triggerPrice)}</dd></div>}
        {levels.invalidationPrice != null && <div><dt>Invalidation</dt><dd>{formatPrice(levels.invalidationPrice)}</dd></div>}
        {levels.riskFromTriggerPct != null && <div><dt>Risk from trigger</dt><dd>{formatPercent(levels.riskFromTriggerPct)}</dd></div>}
      </dl>}
      <div className="decision-reasons">
        {!!decision.strengths?.length && <div><span>Why it qualifies</span><ul>{decision.strengths.map((item) => <li key={item}>{item}</li>)}</ul></div>}
        {!!decision.cautions?.length && <div><span>Watch-outs</span><ul>{decision.cautions.map((item) => <li key={item}>{item}</li>)}</ul></div>}
      </div>
      {!!decision.missingEvidence?.length && <p className="decision-missing"><span>Still unavailable:</span> {decision.missingEvidence.join(', ')}</p>}
      <small className="decision-method">{decision.confidenceMeaning}</small>
    </>}
  </div>
}

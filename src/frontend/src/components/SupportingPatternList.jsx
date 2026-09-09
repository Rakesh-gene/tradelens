import LifecycleBadge from './LifecycleBadge.jsx'

export default function SupportingPatternList({ patterns = [], currentId }) {
  const groups = patterns.filter((item) => item.patternInstanceId !== currentId).reduce((result, pattern) => {
    const key = pattern.patternClass || 'OTHER'
    result[key] = [...(result[key] || []), pattern]
    return result
  }, {})
  if (!Object.keys(groups).length) return <p className="muted-copy">No supporting patterns were active for this security.</p>
  return <div className="supporting-pattern-groups">{Object.entries(groups).map(([group, items]) => <section key={group}><h3>{group}</h3><ul>{items.map((item) => <li key={item.patternInstanceId}><span>{item.variant || item.patternType}</span><LifecycleBadge state={item.state} /></li>)}</ul></section>)}</div>
}

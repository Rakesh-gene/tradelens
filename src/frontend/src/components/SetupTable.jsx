import NavigationLink from './NavigationLink.jsx'
import LifecycleBadge from './LifecycleBadge.jsx'
import { buildPatternPath } from '../routing/routes.js'
import { formatMarketDate, formatPercent, formatPrice, formatScore } from '../utils/formatters.js'
import DecisionSummary from './DecisionSummary.jsx'

const BASE_COLUMNS = [
  ['setupScore', 'Setup'], ['qualityScore', 'Quality'], ['maturityScore', 'Maturity'],
  ['distanceToPivotPct', 'Pivot distance'], ['detectedDate', 'Detected'],
]

export default function SetupTable({ items, filters, onSort, onNavigate }) {
  const hasBestFit = items.some((item) => item.bestFit?.score != null)
  const columns = hasBestFit ? [['bestFit', 'Best fit'], ...BASE_COLUMNS] : BASE_COLUMNS
  return <div className="setup-table-wrap"><table className="setup-table">
    <caption>Setups ranked by server-calculated evidence</caption>
    <thead><tr><th scope="col">Security</th><th scope="col">Pattern</th><th scope="col">Decision</th>{columns.map(([key, label]) => <th scope="col" key={key}><button type="button" onClick={() => onSort(key)} aria-label={`Sort by ${label}${filters.sort === key ? `, currently ${filters.direction}ending` : ''}`}>{label}{filters.sort === key ? (filters.direction === 'asc' ? ' ↑' : ' ↓') : ''}</button></th>)}<th scope="col">Sector</th><th scope="col"><span className="visually-hidden">Action</span></th></tr></thead>
    <tbody>{items.map((setup) => <tr key={setup.patternInstanceId}>
      <th scope="row"><strong>{setup.security?.symbol || setup.security?.isin}</strong><small>{setup.security?.name}</small></th>
      <td><strong>{setup.variant || setup.patternType}</strong><small>{setup.patternClass}</small></td>
      <td>{setup.decision ? <DecisionSummary decision={setup.decision} compact /> : <LifecycleBadge state={setup.state} />}</td>
      {hasBestFit && <td><strong>{formatScore(setup.bestFit?.score)}</strong><small>{setup.bestFit?.tier || 'UNRANKED'} · #{setup.bestFit?.rankWithinState || '—'} of {setup.bestFit?.stateCandidateCount || '—'}</small></td>}
      <td>{formatScore(setup.setupScore)}</td><td>{formatScore(setup.qualityScore)}</td><td>{formatScore(setup.maturityScore)}</td>
      <td>{formatPercent(setup.distanceToPivotPct)}<small>Pivot {formatPrice(setup.pivotPrice)}</small></td>
      <td>{formatMarketDate(setup.detectedDate)}</td><td>{setup.security?.sectorName || setup.security?.sectorId || '—'}</td>
      <td><NavigationLink className="text-button" to={buildPatternPath(setup.patternInstanceId)} onNavigate={onNavigate}>Evidence</NavigationLink></td>
    </tr>)}</tbody>
  </table></div>
}

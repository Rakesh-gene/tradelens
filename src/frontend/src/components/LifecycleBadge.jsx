import { lifecycleTone } from '../utils/presentation.js'

export { lifecycleTone }

export default function LifecycleBadge({ state }) {
  return <span className={`state-badge state-badge--${lifecycleTone(state)}`}><span aria-hidden="true">◆</span>{state || 'UNKNOWN'}</span>
}

export function lifecycleTone(state) {
  if (['MATURE', 'READY', 'RUNNING'].includes(state)) return 'actionable'
  if (['TRIGGERED', 'CONFIRMED', 'COMPLETED'].includes(state)) return 'active'
  if (['FAILED', 'PARTIAL', 'CANCELLED', 'INVALIDATED', 'EXPIRED'].includes(state)) return 'terminal'
  return 'developing'
}

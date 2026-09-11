import { useEffect } from 'react'
import { HEADER_DISCLAIMER } from '../disclaimerCopy'

const AUTO_HIDE_MS = 10_000

export default function LoginDisclaimer({ onDismiss }) {
  useEffect(() => {
    const timer = window.setTimeout(onDismiss, AUTO_HIDE_MS)
    return () => window.clearTimeout(timer)
  }, [onDismiss])

  return <div className="login-disclaimer" role="status" aria-live="polite">
    <p><strong>Investment risk notice:</strong> {HEADER_DISCLAIMER}</p>
    <button type="button" onClick={onDismiss} aria-label="Dismiss risk notice">×</button>
  </div>
}

export { AUTO_HIDE_MS }

import { useEffect, useRef } from 'react'

export default function ConfirmDialog({ open, title, message, confirmLabel = 'Delete', busy = false, onCancel, onConfirm }) {
  const panel = useRef(null)

  useEffect(() => {
    if (!open) return undefined
    const previous = document.activeElement
    panel.current?.querySelector('[data-confirm-action]')?.focus()
    const keydown = (event) => {
      if (event.key === 'Escape' && !busy) onCancel()
      if (event.key !== 'Tab') return
      const focusable = [...panel.current.querySelectorAll('button:not(:disabled)')]
      const first = focusable[0]
      const last = focusable.at(-1)
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus() }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus() }
    }
    document.addEventListener('keydown', keydown)
    return () => { document.removeEventListener('keydown', keydown); previous?.focus?.() }
  }, [open, busy, onCancel])

  if (!open) return null
  return <div className="confirm-dialog-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget && !busy) onCancel() }}>
    <section ref={panel} className="confirm-dialog" role="dialog" aria-modal="true" aria-labelledby="confirm-dialog-title" aria-describedby="confirm-dialog-message">
      <p className="eyebrow">Confirm deletion</p>
      <h2 id="confirm-dialog-title">{title}</h2>
      <p id="confirm-dialog-message">{message}</p>
      <div className="confirm-dialog__actions"><button className="secondary-button" type="button" disabled={busy} onClick={onCancel}>Keep case</button><button className="danger-button" data-confirm-action type="button" disabled={busy} onClick={onConfirm}>{busy ? 'Deleting…' : confirmLabel}</button></div>
    </section>
  </div>
}

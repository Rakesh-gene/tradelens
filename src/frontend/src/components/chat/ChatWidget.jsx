import { useCallback, useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { askEquitySetup, getChatCapabilities } from '../../api/chatApi.js'
import { getPattern } from '../../api/patternApi.js'
import useApiResource from '../../useApiResource.js'
import { formatPrice, formatScore } from '../../utils/formatters.js'
import NavigationLink from '../NavigationLink.jsx'

export default function ChatWidget({ contextSymbol = '', contextPatternId = '', onNavigate, onUnauthorized }) {
  const [open, setOpen] = useState(false)
  const [message, setMessage] = useState('')
  const [response, setResponse] = useState(null)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const dialog = useRef(null)
  const launcher = useRef(null)
  const request = useRef(null)
  const requestSequence = useRef(0)
  const close = useCallback(() => setOpen(false), [])
  const resource = useApiResource(`${open}:${contextSymbol}:${contextPatternId}`, async (signal) => {
    if (!open) return null
    const [capabilities, pattern] = await Promise.all([
      getChatCapabilities({ signal, onUnauthorized }),
      contextPatternId ? getPattern(contextPatternId, { signal, onUnauthorized }) : Promise.resolve(null),
    ])
    return { capabilities, pageSymbol: contextSymbol || pattern?.pattern?.security?.symbol || '' }
  })

  useEffect(() => {
    if (!open) return undefined
    const previous = document.activeElement
    const previousOverflow = document.body.style.overflow
    dialog.current.showModal()
    document.body.style.overflow = 'hidden'
    return () => {
      dialog.current?.close()
      document.body.style.overflow = previousOverflow
      if (previous?.isConnected) previous.focus()
      else launcher.current?.focus()
    }
  }, [open])

  useEffect(() => () => {
    ++requestSequence.current
    request.current?.abort()
  }, [])

  const submit = async (event) => {
    event.preventDefault()
    if (request.current || !message.trim()) return
    const controller = new AbortController()
    const sequence = ++requestSequence.current
    request.current = controller
    setBusy(true)
    setError(null)
    setResponse(null)
    try {
      const answer = await askEquitySetup(message, { contextSymbol: resource.data?.pageSymbol || contextSymbol || undefined, signal: controller.signal, onUnauthorized })
      if (sequence === requestSequence.current) setResponse(answer)
    } catch (failure) {
      if (sequence === requestSequence.current && failure.name !== 'AbortError') {
        setError(failure.status === 404 && failure.code === 'REQUEST_FAILED'
          ? new Error('The running backend does not expose chat yet. An administrator needs to restart the backend with the updated code.') : failure)
      }
    } finally {
      if (sequence === requestSequence.current) { setBusy(false); request.current = null }
    }
  }
  const navigateFromChat = (path) => { close(); onNavigate(path) }
  const available = resource.status === 'success' && resource.data?.capabilities?.enabled
  const maxMessageLength = resource.data?.capabilities?.maxMessageLength || 4000

  return <>
    <button ref={launcher} type="button" className="primary-button chat-launcher" onClick={() => setOpen(true)} aria-haspopup="dialog" aria-expanded={open} aria-controls="equity-chat-window">
      <svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M5 5h14v10H9l-4 4V5Z" /><path d="M9 9h6M9 12h4" /></svg>
      <span>AI</span>
    </button>
    {open && createPortal(<dialog ref={dialog} id="equity-chat-window" className="chat-window" aria-labelledby="equity-chat-title" onCancel={(event) => { event.preventDefault(); close() }}>
      <header className="chat-window-header">
        <div className="chat-window-title">
          <h2 id="equity-chat-title">AI</h2>
          {available && <svg className="chat-availability" role="img" aria-label="Assistant available" viewBox="0 0 20 20" fill="none"><circle cx="10" cy="10" r="8" /><path d="m6 10 3 3 5-6" /></svg>}
        </div>
        <button type="button" className="secondary-button chat-close" onClick={close} aria-label="Close AI">
          <svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18" /></svg>
        </button>
      </header>
      <div className="chat-transcript" aria-busy={busy}>
        {resource.error && <div role="alert"><p>{resource.error.message}</p><button type="button" className="secondary-button" onClick={resource.reload}>Retry connection</button></div>}
        {busy && <p role="status">Reading the equity's setup evidence…</p>}
        {error && <p role="alert">{error.message}</p>}
        {response && <section aria-label="Setup answer">
          <p role="status">Answer ready for {response.security.symbol}.</p>
          <h3>{response.security.symbol} · {response.security.name}</h3>
          <p><strong>Evidence as of {response.dataAsOf || 'unavailable'}</strong></p>
          <p>{response.answer}</p>
          {response.isStale && <span className="chat-status">Earlier-session evidence</span>}
          {response.isPartial && <span className="chat-status">Partial evidence</span>}
          {response.warnings?.map((warning) => <p className="muted-copy" key={warning}>{warning}</p>)}
          {response.setups.map((setup) => <article className="chat-setup-card" key={setup.patternInstanceId}>
            <h4>{setup.variant || setup.patternType} <span className="chat-status">{setup.state}</span></h4>
            <p className="muted-copy">Daily · Detected {setup.detectedDate} · Evidence {setup.dataAsOf}</p>
            <dl className="chat-facts">
              {Object.entries(setup.scores).map(([label, value]) => <div key={label}><dt>{label} score</dt><dd>{value == null ? 'Unavailable' : `${formatScore(value)} / 100`}</dd></div>)}
              {Object.entries(setup.levels).map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value == null ? 'Unavailable' : formatPrice(value)}</dd></div>)}
            </dl>
            <NavigationLink to={setup.href} onNavigate={navigateFromChat}>View setup evidence</NavigationLink>
          </article>)}
          <NavigationLink to={response.security.href} onNavigate={navigateFromChat}>Open equity overview</NavigationLink>
          <p className="muted-copy">{response.disclaimer}</p>
        </section>}
      </div>
      <form className="chat-composer" onSubmit={submit}>
        <label className="visually-hidden" htmlFor="chat-question">Your question</label>
        <textarea id="chat-question" value={message} onChange={(event) => setMessage(event.target.value)} placeholder="Message…" rows={3} maxLength={maxMessageLength} disabled={busy} />
        <div className="chat-composer-footer">
          <button className="primary-button" type="submit" disabled={busy || !message.trim()}>{busy ? 'Sending…' : 'Send'}</button>
        </div>
      </form>
    </dialog>, document.body)}
  </>
}

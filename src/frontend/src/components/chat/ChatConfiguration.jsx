import { useRef, useState, useEffect } from 'react'
import { getChatConfiguration, saveChatConfiguration } from '../../api/chatApi.js'
import useApiResource from '../../useApiResource.js'

export default function ChatConfiguration({ onUnauthorized, onSaved }) {
  const [settings, setSettings] = useState(null)
  const [apiKey, setApiKey] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [notice, setNotice] = useState('')
  const request = useRef(null)
  const resource = useApiResource('chat-configuration', (signal) => getChatConfiguration({ signal, onUnauthorized }))
  useEffect(() => { if (resource.data) setSettings(resource.data.configuration) }, [resource.data])
  useEffect(() => () => request.current?.abort(), [])
  const update = (key, value) => setSettings((current) => ({ ...current, [key]: value }))
  const save = async (event) => {
    event.preventDefault()
    if (request.current) return
    const controller = new AbortController()
    request.current = controller
    setBusy(true); setError(null); setNotice('')
    try {
      const result = await saveChatConfiguration({ enabled: settings.enabled, provider: settings.provider ?? 'gemini', ollamaUrl: settings.ollamaUrl ?? 'http://127.0.0.1:11434', model: settings.model, ontologyUrl: settings.ontologyUrl, timeoutSeconds: settings.timeoutSeconds ?? 45, ...(apiKey ? { apiKey } : {}) }, { signal: controller.signal, onUnauthorized })
      if (!controller.signal.aborted) {
        setApiKey(''); setSettings(result.configuration)
        setNotice('Configuration saved and applied.'); onSaved()
      }
    } catch (failure) { if (!controller.signal.aborted) setError(failure) }
    finally { if (!controller.signal.aborted) { setBusy(false); request.current = null } }
  }
  return <section className="chat-configuration" aria-label="Chat configuration">
    <h3>Chat configuration</h3>
    {resource.status === 'loading' && <p role="status">Loading settings…</p>}
    {resource.error && <div role="alert"><p>{resource.error.message}</p><button type="button" className="secondary-button" onClick={resource.reload}>Retry settings</button></div>}
    {settings && <form className="chat-settings-form" onSubmit={save}>
      <label><input type="checkbox" checked={settings.enabled} disabled={busy} onChange={(event) => update('enabled', event.target.checked)} /> Enable chat</label>
      <label htmlFor="chat-provider">Model provider</label>
      <select id="chat-provider" value={settings.provider ?? 'gemini'} disabled={busy} onChange={(event) => setSettings((current) => ({ ...current, provider: event.target.value, model: event.target.value === 'ollama' ? 'gemma4:31b-cloud' : '' }))}>
        <option value="ollama">Ollama</option><option value="gemini">Gemini</option>
      </select>
      <label htmlFor="chat-model">Chat model</label>
      <input id="chat-model" value={settings.model} disabled={busy} onChange={(event) => update('model', event.target.value)} placeholder="gemma4:31b-cloud" maxLength={200} required />
      {settings.provider === 'ollama' ? <>
        <label htmlFor="chat-ollama-url">Ollama endpoint</label>
        <input id="chat-ollama-url" type="url" value={settings.ollamaUrl ?? 'http://127.0.0.1:11434'} disabled={busy} onChange={(event) => update('ollamaUrl', event.target.value)} required maxLength={2048} />
        <small className="muted-copy">Cloud models use the Ollama server's signed-in account. No Gemini key is required.</small>
      </> : <>
      <label htmlFor="chat-gemini-key">Gemini API key</label>
      <input id="chat-gemini-key" type="password" value={apiKey} disabled={busy} onChange={(event) => setApiKey(event.target.value)} placeholder={settings.apiKeyConfigured ? 'Key saved — leave blank to keep it' : 'Enter your Gemini API key'} autoComplete="new-password" maxLength={4096} />
      <small className="muted-copy">{settings.apiKeyConfigured ? 'A key is saved on the server.' : 'No key has been saved.'} The saved key is never returned to this form.</small>
      </>}
      <label htmlFor="chat-ontology-url">Ontology endpoint</label>
      <input id="chat-ontology-url" type="url" value={settings.ontologyUrl} disabled={busy} onChange={(event) => update('ontologyUrl', event.target.value)} required maxLength={2048} />
      <label htmlFor="chat-gemini-timeout">Model timeout (seconds)</label>
      <input id="chat-gemini-timeout" type="number" min={5} max={120} step={1} value={settings.timeoutSeconds ?? 45} disabled={busy} onChange={(event) => update('timeoutSeconds', Number(event.target.value))} required />
      <button className="primary-button" type="submit" disabled={busy}>{busy ? 'Saving…' : 'Save configuration'}</button>
      <p className="muted-copy">These settings apply to the whole application. Saving applies them immediately; connection availability is checked when you ask a question.</p>
    </form>}
    {error && <p role="alert">{error.message}</p>}
    {notice && <p role="status">{notice}</p>}
  </section>
}

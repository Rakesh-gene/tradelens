import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import ChatWidget from './ChatWidget.jsx'
import answer from '../../../test/fixtures/chat-equity-setup.json'

const { ask, capabilities } = vi.hoisted(() => ({ ask: vi.fn(), capabilities: vi.fn() }))
vi.mock('../../api/chatApi.js', () => ({ askEquitySetup: ask, getChatCapabilities: capabilities }))
vi.mock('../../api/patternApi.js', () => ({ getPattern: vi.fn() }))

beforeAll(() => {
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', ''); this.querySelector('button')?.focus() }
  HTMLDialogElement.prototype.close = function () { this.removeAttribute('open') }
})

describe('Chat widget', () => {
  beforeEach(() => { ask.mockReset(); capabilities.mockReset(); capabilities.mockResolvedValue({ enabled: true, configuration: { checks: [{ setting: 'CHAT_ENABLED', label: 'Chat feature', status: 'configured' }], help: 'Configuration help' } }); window.history.replaceState({}, '', '/securities/RELIANCE') })

  it('opens an overlay without navigation, answers the one question and preserves it on reopen', async () => {
    ask.mockResolvedValue(answer)
    render(<ChatWidget contextSymbol="RELIANCE" onNavigate={vi.fn()} />)
    const launcher = screen.getByRole('button', { name: 'AI' })
    await userEvent.click(launcher)
    expect(screen.getByRole('dialog', { name: 'AI' })).toBeTruthy()
    expect(window.location.pathname).toBe('/securities/RELIANCE')
    expect(screen.getByLabelText('Your question').value).toBe('')
    expect(screen.getByRole('button', { name: 'Send' }).disabled).toBe(true)
    expect(await screen.findByRole('img', { name: 'Assistant available' })).toBeTruthy()
    expect(screen.queryByText('Configuration status')).toBeNull()
    expect(screen.queryByText('Configuration help')).toBeNull()
    expect(screen.queryByRole('button', { name: 'Use suggested question' })).toBeNull()
    expect(screen.queryByText(/Page context:|characters|EOD analysis/)).toBeNull()
    fireEvent.change(screen.getByLabelText('Your question'), { target: { value: 'How is Reliance looking?' } })
    await userEvent.click(screen.getByRole('button', { name: 'Send' }))
    expect(await screen.findByText('Recorded setup evidence.')).toBeTruthy()
    expect(screen.getByText('Evidence as of 2026-10-30')).toBeTruthy()
    expect(screen.getByText('Unavailable')).toBeTruthy()
    expect(screen.getByText('Earlier-session evidence')).toBeTruthy()
    expect(ask.mock.calls[0][0]).toBe('How is Reliance looking?')
    expect(ask.mock.calls[0][1].contextSymbol).toBe('RELIANCE')
    expect(screen.queryByLabelText('NSE equity symbol')).toBeNull()
    await userEvent.click(screen.getByRole('button', { name: 'Close AI' }))
    expect(document.activeElement).toBe(launcher)
    await userEvent.click(launcher)
    expect(screen.getByText('Recorded setup evidence.')).toBeTruthy()
  })

  it('hides the availability icon when disabled and supports Escape dismissal', async () => {
    capabilities.mockResolvedValue({ enabled: false })
    render(<ChatWidget onNavigate={vi.fn()} />)
    await userEvent.click(screen.getByRole('button', { name: 'AI' }))
    await waitFor(() => expect(capabilities).toHaveBeenCalled())
    expect(screen.queryByRole('img', { name: 'Assistant available' })).toBeNull()
    expect(screen.queryByText(/assistant is not configured yet/)).toBeNull()
    fireEvent(screen.getByRole('dialog'), new Event('cancel', { bubbles: false, cancelable: true }))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(document.body.style.overflow).toBe('')
    expect(ask).not.toHaveBeenCalled()
  })

  it('prevents duplicate sends and shows retryable failures', async () => {
    let reject
    ask.mockImplementation(() => new Promise((resolve, fail) => { reject = fail }))
    render(<ChatWidget contextSymbol="RELIANCE" onNavigate={vi.fn()} />)
    await userEvent.click(screen.getByRole('button', { name: 'AI' }))
    fireEvent.change(screen.getByLabelText('Your question'), { target: { value: 'How is Reliance looking?' } })
    const send = await screen.findByRole('button', { name: 'Send' })
    await waitFor(() => expect(send.disabled).toBe(false))
    await userEvent.dblClick(send)
    expect(ask).toHaveBeenCalledTimes(1)
    reject(new Error('Ontology unavailable'))
    expect(await screen.findByRole('alert')).toHaveProperty('textContent', 'Ontology unavailable')
    expect(screen.getByRole('button', { name: 'Send' }).disabled).toBe(false)
  })

  it('submits a natural question with no symbol input even when configuration is unavailable', async () => {
    capabilities.mockResolvedValue({ enabled: false })
    ask.mockRejectedValue(new Error('Configure Gemini first'))
    render(<ChatWidget onNavigate={vi.fn()} />)
    await userEvent.click(screen.getByRole('button', { name: 'AI' }))
    fireEvent.change(screen.getByLabelText('Your question'), { target: { value: 'what is the setup in reliance today?' } })
    await userEvent.click(screen.getByRole('button', { name: 'Send' }))
    expect(ask.mock.calls[0][0]).toBe('what is the setup in reliance today?')
    expect(await screen.findByRole('alert')).toHaveProperty('textContent', 'Configure Gemini first')
    expect(screen.getByLabelText('Your question').maxLength).toBe(4000)
  })

  it('has no settings even for administrators and closes with an icon', async () => {
    render(<ChatWidget isAdmin onNavigate={vi.fn()} />)
    await userEvent.click(screen.getByRole('button', { name: 'AI' }))
    expect(screen.queryByRole('button', { name: 'Settings' })).toBeNull()
    const close = screen.getByRole('button', { name: 'Close AI' })
    expect(close.textContent).toBe('')
    expect(close.querySelector('svg')).toBeTruthy()
    await userEvent.click(close)
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('shows Ontop facts with an explicit warning when Gemini is unavailable', async () => {
    ask.mockResolvedValue({ ...answer, isPartial: true,
      warnings: ['Gemini explanation unavailable. Showing validated Ontop evidence only; no LLM explanation was generated.'],
      provenance: { ...answer.provenance, model: null, answerMode: 'ontologyEvidenceOnly' } })
    render(<ChatWidget contextSymbol="RELIANCE" onNavigate={vi.fn()} />)
    await userEvent.click(screen.getByRole('button', { name: 'AI' }))
    fireEvent.change(screen.getByLabelText('Your question'), { target: { value: 'How is Reliance looking?' } })
    await userEvent.click(screen.getByRole('button', { name: 'Send' }))
    expect(await screen.findByText(/Gemini explanation unavailable/)).toBeTruthy()
    expect(screen.getByText('Recorded setup evidence.')).toBeTruthy()
    expect(screen.getByRole('link', { name: 'View setup evidence' })).toBeTruthy()
    expect(screen.queryByText('Evidence lineage')).toBeNull()
    expect(screen.queryByText(/engine .*configuration .*features .*adjustments /)).toBeNull()
  })
})

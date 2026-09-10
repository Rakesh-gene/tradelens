import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import DecisionSummary from './DecisionSummary.jsx'

const decision = {
  actionLabel: 'Ready', tone: 'action', confidenceBand: 'HIGH', confidenceScore: 87,
  headline: 'Ready — high-quality two-contraction VCP',
  summary: 'The two-contraction VCP is ready and waiting for a valid breakout.',
  nextStep: 'Wait for a decisive close above the trigger; do not anticipate it.',
  strengths: ['Relative strength is leading the peer universe'], cautions: ['Market context is mixed'],
  missingEvidence: [], confidenceMeaning: 'Evidence alignment and completeness, not historical probability.',
  levels: { triggerPrice: 1500, invalidationPrice: 1425, riskFromTriggerPct: 5 },
}

describe('DecisionSummary', () => {
  it('leads with the operating decision and keeps evidence explainable', () => {
    render(<DecisionSummary decision={decision} />)
    expect(screen.getByText('Ready — high-quality two-contraction VCP')).toBeTruthy()
    expect(screen.getByText(/Wait for a decisive close/)).toBeTruthy()
    expect(screen.getByText('Relative strength is leading the peer universe')).toBeTruthy()
    expect(screen.getByText(/not historical probability/)).toBeTruthy()
  })

  it('keeps compact decisions concise', () => {
    render(<DecisionSummary decision={decision} compact />)
    expect(screen.getByText(/HIGH confidence/)).toBeTruthy()
    expect(screen.getByText(/Wait for a decisive close/)).toBeTruthy()
    expect(screen.queryByText('Relative strength is leading the peer universe')).toBeNull()
  })
})

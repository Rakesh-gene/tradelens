import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import PatternMeasurements from './PatternMeasurements.jsx'

describe('PatternMeasurements', () => {
  it('rounds displayed decimals and hides internal quality components', () => {
    render(<PatternMeasurements patternType="BRK-52WH" values={{
      pivot_distance_pct: 1.23456,
      quality_components: { proximity: 24.98765 },
    }} />)

    expect(screen.getByText('1.235')).toBeTruthy()
    expect(screen.queryByText('Quality Components')).toBeNull()
    expect(screen.queryByText(/24\.98765/)).toBeNull()
  })
})

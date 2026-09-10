import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import SiteFooter from './SiteFooter.jsx'

describe('SiteFooter', () => {
  it('shows one concise market-risk disclaimer', () => {
    render(<SiteFooter />)

    expect(screen.getByRole('contentinfo')).toBeTruthy()
    expect(screen.getByText(/not investment advice/i)).toBeTruthy()
    expect(screen.getByText(/loss of capital/i)).toBeTruthy()
  })
})

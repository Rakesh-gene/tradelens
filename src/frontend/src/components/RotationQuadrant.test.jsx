import React from 'react'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import RotationQuadrant from './RotationQuadrant.jsx'

const items = [
  { id: 'one', name: 'One', rotation: { strength: 4, momentum: 2, zone: 'LEADING', trail: [{ strength: 2, momentum: 1 }, { strength: 4, momentum: 2 }] } },
  { id: 'two', name: 'Two', rotation: { strength: -4, momentum: -2, zone: 'LAGGING', trail: [{ strength: -2, momentum: -1 }, { strength: -4, momentum: -2 }] } },
]

describe('RotationQuadrant', () => {
  it('fades every other path and marker while one item is hovered', async () => {
    const { container } = render(<RotationQuadrant title="Rotation" description="Test" items={items} itemId={(item) => item.id} itemLabel={(item) => item.name} onOpen={vi.fn()} emptyMessage="None" ariaLabel="Rotation chart" />)

    await userEvent.hover(screen.getByRole('button', { name: /One: Leading/ }))

    const trails = container.querySelectorAll('.watchlist-quadrant__trail')
    const points = container.querySelectorAll('.watchlist-quadrant__point')
    expect(trails[0].className.baseVal).toContain('is-highlighted')
    expect(trails[1].className.baseVal).toContain('is-muted')
    expect(points[0].className).toContain('is-highlighted')
    expect(points[1].className).toContain('is-muted')
  })
})

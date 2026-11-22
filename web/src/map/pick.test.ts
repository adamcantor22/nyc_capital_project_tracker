import { describe, expect, it } from 'vitest'
import { pickNearest } from './pick'

describe('tap tolerance', () => {
  const at = { x: 100, y: 100 }
  it('selects a point centred within the margin though the tap misses its disc', () => {
    expect(pickNearest([{ id: 'small', x: 110, y: 100, direct: false }], at, 14)).toBe('small')
  })
  it('ignores points beyond the margin that the tap does not touch', () => {
    expect(pickNearest([{ id: 'far', x: 120, y: 100, direct: false }], at, 14)).toBeNull()
  })
  it('prefers the nearest centre, so a small point beside a large one can be picked', () => {
    const cands = [{ id: 'big', x: 130, y: 100, direct: true }, { id: 'small', x: 92, y: 100, direct: false }]
    expect(pickNearest(cands, at, 14)).toBe('small')
  })
  it('keeps a direct hit on a large point whose centre is beyond the margin', () => {
    expect(pickNearest([{ id: 'big', x: 130, y: 100, direct: true }], at, 14)).toBe('big')
  })
})

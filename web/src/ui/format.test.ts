import { describe, expect, it } from 'vitest'
import { whenLabel } from './format'

describe('whenLabel', () => {
  const now = new Date(2026, 9, 3)
  it('reads start and finish in one line', () => {
    expect(whenLabel('2022-03-15', '2027-06-30', false, now)).toBe('Started Mar 2022 · due Jun 2027, in 8 mo')
    expect(whenLabel(null, '2025-06-30', false, now)).toBe('Due Jun 2025 (date has passed)')
    expect(whenLabel('2020-01-01', '2024-12-01', true, now)).toBe('Started Jan 2020 · finished Dec 2024')
    expect(whenLabel(null, null, false, now)).toBeNull()
  })
})

import { describe, expect, it } from 'vitest'
import { whenLabel } from './format'

const none = { designStart: null, designEnd: null, constructionStart: null, constructionEnd: null, phaseStart: null }
const w = (over: object) => ({ phase: 'Construction', phaseGroup: 'Active', startDate: null, forecastCompletion: null, milestones: none, ...over })

describe('whenLabel', () => {
  const now = new Date(2026, 9, 3)
  it('leads with the phase, then its dates', () => {
    expect(whenLabel(w({ phase: 'Close-out', forecastCompletion: '2022-06-02', milestones: { ...none, constructionEnd: '2022-06-02' } }), now))
      .toBe('Construction finished Jun 2022; in close-out (final inspections and payments)')
    expect(whenLabel(w({ forecastCompletion: '2031-05-27', milestones: { ...none, constructionStart: '2025-03-03' } }), now))
      .toBe('In construction since Mar 2025, due May 2031 (in 4 yr 7 mo)')
    expect(whenLabel(w({ phase: 'Design', forecastCompletion: '2029-09-01', milestones: { ...none, designStart: '2022-08-30' } }), now))
      .toBe('In design since Aug 2022, finish forecast Sep 2029')
  })
  it('trusts the phase over a contradicting milestone, and says when a forecast has passed', () => {
    expect(whenLabel(w({ forecastCompletion: '2024-02-18', milestones: { ...none, constructionStart: '2023-04-25', constructionEnd: '2024-04-22' } }), now))
      .toBe('In construction since Apr 2023, forecast finish Feb 2024 has passed')
  })
  it('handles done, not started and missing dates', () => {
    expect(whenLabel(w({ phase: '(Completed)', phaseGroup: 'Done', forecastCompletion: '2024-12-01' }), now)).toBe('Finished Dec 2024')
    expect(whenLabel(w({ phase: '(Pending)', phaseGroup: 'Not started' }), now)).toBe('Not started')
    expect(whenLabel(w({ phase: '(Partner-managed)', phaseGroup: 'Partner-managed' }), now)).toBeNull()
  })
})

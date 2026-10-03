import { describe, expect, it } from 'vitest'
import type { ScheduleSnap } from './data'
import { slipSummary } from './schedule'

const snap = (period: number, date: string, type = 'Forecast'): ScheduleSnap => ({
  period, phase: null, completion_date: date, completion_type: type, variance_days: null, variance_implausible: false, reason: null,
})

describe('slipSummary', () => {
  it('says how far the forecast moved', () => {
    expect(slipSummary([snap(202305, '2024-05-01'), snap(202401, '2025-12-01')])).toBe(
      'Forecast to finish Dec 2025: 19 months later than forecast in May 2023.')
    expect(slipSummary([snap(202305, '2024-05-01'), snap(202309, '2024-05-20')])).toBe(
      'Forecast to finish May 2024, unchanged since May 2023.')
  })
  it('reports completion against the first forecast', () => {
    expect(slipSummary([snap(202305, '2024-05-01'), snap(202409, '2024-08-01', 'Actual')])).toBe(
      'Completed Aug 2024, 3 months later than first forecast.')
  })
})

import { describe, expect, it } from 'vitest'
import { toProject, type NycCapitalRow } from '../data/programs/nycCapital'
import { inBox, summarize } from './aggregate'

const base = { program: 'nyc_capital', title: 'T', agency_project_name: null, description: null, managing_agencies: ['DDC'], sponsor_agency: null, pids: [], borough: 'Queens', community_board: null, category: null, budget_line: null, subtheme: null, phase: null, has_schedule: false, forecast_completion: null, budget_city: null, spend_pct: null, first_reported: 202305, last_reported: 202605, status: 'current', source: null, matched_to: null, source_flag: null, spread_m: null, n_points: 1, outside_nyc: null, district: null, districts: [], neighborhood: null } as const
const mk = (o: Partial<NycCapitalRow>) => toProject({ ...base, fms_id: 'X', theme: 'Parks', phase_group: 'Active', budget: 10, spend: 4, budget_non_city: 0, budget_change: null, tier: 'A', on_map: true, approximate: false, lon: -73.9, lat: 40.7, ...o } as NycCapitalRow)

describe('aggregate', () => {
  const ps = [
    mk({ fms_id: 'a', budget_change: 2 }),
    mk({ fms_id: 'b', theme: 'Health', budget: 30, budget_non_city: 5, budget_change: -1, tier: 'B', approximate: true, lon: -73.95 }),
    mk({ fms_id: 'c', tier: 'D', on_map: false, lon: -73.9 }),
    mk({ fms_id: 'd', lon: -74.1 }),
  ]
  it('keeps pinned projects inside the box only', () => {
    expect(inBox(ps, { w: -74, e: -73.8, s: 40.6, n: 40.8 }).map((p) => p.id)).toEqual(['a', 'b'])
  })
  it('sums money, signed change and groups', () => {
    const s = summarize(inBox(ps, { w: -74, e: -73.8, s: 40.6, n: 40.8 }))
    expect([s.n, s.budget, s.spend, s.change, s.changed, s.nonCity, s.approximate]).toEqual([2, 40, 8, 1, 2, 5, 1])
    expect(s.byTheme).toEqual([['Health', 30], ['Parks', 10]])
  })
})

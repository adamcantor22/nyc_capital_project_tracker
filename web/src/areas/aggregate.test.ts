import { describe, expect, it } from 'vitest'
import { toProject, type NycCapitalRow } from '../data/programs/nycCapital'
import { aggregateAreas, type Site } from './aggregate'
import { colorFor } from './measures'

const base = { program: 'nyc_capital', title: 'T', agency_project_name: null, description: null, managing_agencies: ['DDC'], sponsor_agency: null, pids: [], community_board: null, category: null, budget_line: null, theme: 'Parks', subtheme: null, phase: null, phase_group: 'Active', has_schedule: false, forecast_completion: null, budget_city: null, budget_non_city: 0, spend: 0, spend_pct: null, budget_change: null, first_reported: 202305, last_reported: 202605, status: 'current', source: null, lon: 0, lat: 0, matched_to: null, source_flag: null, spread_m: null, n_points: 1, on_map: true, approximate: false, outside_nyc: null, district: null, districts: [], neighborhood: null } as const
const mk = (o: Partial<NycCapitalRow>) => toProject({ ...base, fms_id: 'X', borough: 'Brooklyn', budget: 100, tier: 'A', ...o } as NycCapitalRow)

describe('area aggregation', () => {
  const ps = [
    mk({ fms_id: 'a' }),
    mk({ fms_id: 'two', budget: 200 }),
    mk({ fms_id: 'd', tier: 'D', budget: 50 }),
    mk({ fms_id: 'e', tier: 'E', budget: 10 }),
    mk({ fms_id: 'u', tier: 'Unplaced', borough: null, budget: 999 }),
  ]
  const sites = new Map<string, Site[]>([
    ['a', [{ fms_id: 'a', share: 1, district: 301, nta: 'Park Slope' }]],
    ['two', [{ fms_id: 'two', share: 0.5, district: 301, nta: 'Park Slope' }, { fms_id: 'two', share: 0.5, district: 302, nta: 'Red Hook' }]],
    ['d', [{ fms_id: 'd', share: 1, district: 302, nta: 'Red Hook' }]],
    ['e', [{ fms_id: 'e', share: 1, district: 303, nta: 'Bushwick' }]],
  ])
  it('counts each level only from projects located at least that precisely', () => {
    const b = aggregateAreas('boroughs', ps, sites).get('Brooklyn')!
    expect([b.n, b.budget]).toEqual([4, 360])
    const d = aggregateAreas('districts', ps, sites)
    expect([d.get('301')!.budget, d.get('302')!.budget, d.has('303')]).toEqual([200, 150, false])
    const n = aggregateAreas('neighborhoods', ps, sites)
    expect([n.get('Red Hook')!.budget, n.get('Red Hook')!.n]).toEqual([100, 1])
  })
  it('colours sequential and diverging values', () => {
    expect(colorFor('seq', 0, 10, 0)).toBe('#e3eefb')
    expect(colorFor('seq', 10, 10, 0)).toBe('#0d366b')
    expect(colorFor('div', 0, 5, -5)).toBe('#f0efec')
    expect(colorFor('div', -5, 5, -5)).toBe('#1c5cab')
  })
})

import { describe, expect, it } from 'vitest'
import { toProject, type NycCapitalRow } from '../data/programs/nycCapital'
import { applyFilters, budgetBand, optionCounts } from './registry'
import { money, total, measureById } from '../measures/registry'

const row = (over: Partial<NycCapitalRow>): NycCapitalRow => ({
  program: 'nyc_capital', fms_id: 'X1', title: 'T', agency_project_name: null, description: null,
  managing_agencies: ['DDC'], sponsor_agency: null, pids: [], borough: 'Queens', community_board: 'Queens',
  category: null, budget_line: null, theme: 'Parks', subtheme: null, phase: 'Design', phase_group: 'Active',
  has_schedule: true, forecast_completion: null, budget: 5e6, budget_city: 4e6, budget_non_city: 1e6,
  spend: 1e6, spend_pct: 20, budget_change: -2e5, first_reported: 202305, last_reported: 202605,
  status: 'current', tier: 'A', source: 'cpdb', lon: -73.9, lat: 40.7, matched_to: null, source_flag: null,
  spread_m: null, n_points: 1, on_map: true, approximate: false, outside_nyc: null, district: 401,
  districts: [401], neighborhood: null, ...over,
})

const ps = [
  toProject(row({})),
  toProject(row({ fms_id: 'X2', theme: 'Health', borough: 'Bronx', budget: 2e9, managing_agencies: ['DDC', 'DOT'] })),
  toProject(row({ fms_id: 'X3', theme: 'Parks', status: 'dropped', budget_change: null })),
]

describe('filters', () => {
  it('ANDs filters and ORs values within one', () => {
    expect(applyFilters(ps, { theme: ['Parks'], status: ['current'] }).map((p) => p.id)).toEqual(['X1'])
    expect(applyFilters(ps, { agency: ['DOT', 'XYZ'] }).map((p) => p.id)).toEqual(['X2'])
    expect(applyFilters(ps, { theme: [] })).toHaveLength(3)
  })
  it('counts options under the other filters only', () => {
    expect(optionCounts(ps, { theme: ['Parks'], status: ['current'] }, 'theme')).toEqual([['Health', 1], ['Parks', 1]])
    expect(optionCounts(ps, {}, 'status')).toEqual([['current', 2], ['dropped', 1]])
  })
  it('bands budgets', () => {
    expect(budgetBand(5e6)).toBe('$1M–$10M')
    expect(budgetBand(2e9)).toBe('$1B and up')
  })
})

describe('measures', () => {
  it('totals and formats signed money', () => {
    expect(total(ps, measureById.city)).toBe(12e6)
    expect(money(-2e5, true)).toBe('−$200K')
    expect(money(1.5e9, true)).toBe('+$1.5B')
    expect(money(null)).toBe('—')
  })
})

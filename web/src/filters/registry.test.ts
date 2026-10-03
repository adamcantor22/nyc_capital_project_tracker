import { describe, expect, it } from 'vitest'
import { toProject, type NycCapitalRow } from '../data/programs/nycCapital'
import { applyFilters, budgetBand, optionCounts, pick, pickSub, pickTheme } from './registry'
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

describe('legend taps', () => {
  it('solos on tap, clears on a second tap, adds on hold', () => {
    expect(pick(['Parks'], ['Health'], false)).toEqual(['Health'])
    expect(pick(['Health'], ['Health'], false)).toEqual([])
    expect(pick(['Parks'], ['Health'], true)).toEqual(['Parks', 'Health'])
    expect(pick(['Parks', 'Health'], ['Health'], true)).toEqual(['Parks'])
    expect(pick([], ['Education', 'Housing'], false)).toEqual(['Education', 'Housing'])
  })
})

describe('theme and subtheme', () => {
  const tp = [
    toProject(row({ fms_id: 'B1', theme: 'Transportation', subtheme: 'Bridges' })),
    toProject(row({ fms_id: 'S1', theme: 'Transportation', subtheme: 'Streets' })),
    toProject(row({ fms_id: 'T0', theme: 'Transportation', subtheme: null })),
    toProject(row({ fms_id: 'P1', theme: 'Parks' })),
  ]
  const sibs = ['Bridges', 'Streets', 'Other transportation']
  const subsOf = (t: string) => (t === 'Transportation' ? sibs : [])
  const ids = (f: Record<string, string[]>) => applyFilters(tp, f).map((p) => p.id)

  it('ORs a whole theme with another theme\'s subthemes', () => {
    expect(ids({ theme: ['Parks'], subtheme: ['Bridges'] })).toEqual(['B1', 'P1'])
    expect(ids({ subtheme: ['Other transportation'] })).toEqual(['T0'])
  })
  it('keeps every theme countable while a subtheme is picked', () => {
    expect(optionCounts(tp, { subtheme: ['Bridges'] }, 'theme')).toEqual([['Transportation', 3], ['Parks', 1]])
  })
  it('picks a subtheme without its theme, and adds a theme alongside', () => {
    let f = pickSub({}, 'Transportation', 'Bridges', sibs, false)
    expect(f).toEqual({ theme: [], subtheme: ['Bridges'] })
    f = pickTheme(f, ['Parks'], true, subsOf)
    expect(ids(f)).toEqual(['B1', 'P1'])
  })
  it('splits a whole theme when one subtheme is removed, and rejoins it', () => {
    let f = pickSub({ theme: ['Transportation'] }, 'Transportation', 'Bridges', sibs, true)
    expect(f).toEqual({ theme: [], subtheme: ['Streets', 'Other transportation'] })
    f = pickSub(f, 'Transportation', 'Bridges', sibs, true)
    expect(f).toEqual({ theme: ['Transportation'], subtheme: [] })
  })
  it('tapping the only subtheme goes back to its whole theme; tapping a theme drops its split', () => {
    expect(pickSub({ subtheme: ['Bridges'] }, 'Transportation', 'Bridges', sibs, false)).toEqual({ theme: ['Transportation'], subtheme: [] })
    expect(pickTheme({ subtheme: ['Bridges'] }, ['Transportation'], false, subsOf)).toEqual({ theme: ['Transportation'], subtheme: [] })
    expect(pickTheme({ theme: ['Parks'] }, ['Parks'], false, subsOf)).toEqual({ theme: [], subtheme: [] })
  })
})

describe('active chips', () => {
  it('groups a theme with its subthemes and hides defaults', async () => {
    const { activeChips } = await import('./chips')
    const chips = activeChips({ status: ['current'], theme: ['Parks'], subtheme: ['Bridges'], agency: ['DEP'] })
    expect(chips.map((c) => [c.key, c.label, c.values.length])).toEqual([['theme', 'Theme', 2], ['agency', 'Agency', 1]])
  })
})

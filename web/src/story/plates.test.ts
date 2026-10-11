import { describe, expect, it } from 'vitest'
import type { Site } from '../areas/aggregate'
import { toProject, type NycCapitalRow } from '../data/programs/nycCapital'
import type { Project } from '../data/types'
import { boroughJails, districtMoney, largestPlaced, leadProjectIn, megaProject, programTotals } from './plates'

const base = { program: 'nyc_capital', title: 'T', agency_project_name: null, description: null, managing_agencies: ['DDC'], sponsor_agency: null, pids: [], community_board: null, category: null, budget_line: null, theme: 'Parks', subtheme: null, phase: null, phase_group: 'Active', has_schedule: false, forecast_completion: null, budget_city: null, budget_non_city: 0, spend: 0, spend_pct: null, budget_change: null, first_reported: 202305, last_reported: 202605, status: 'current', source: null, lon: -73.9, lat: 40.7, matched_to: null, source_flag: null, spread_m: null, n_points: 1, on_map: true, approximate: false, outside_nyc: null, district: null, districts: [], neighborhood: null } as const
const city = (o: Partial<NycCapitalRow>) => toProject({ ...base, fms_id: 'X', borough: 'Brooklyn', budget: 100, tier: 'A', ...o } as NycCapitalRow)
const other = (p: Project, program: string, o: Partial<Project> = {}): Project => ({ ...p, program, ...o })
const site = (district: number, share = 1): Site => ({ lon: -73.9, lat: 40.7, share, share_method: 'equal', district, nta: 'Red Hook' })

describe('story plates', () => {
  it('totals each program once, leaving out SCA work a city record counts', () => {
    const ps = [city({ fms_id: 'c1' }), other(city({ fms_id: 's1', budget: 50 }), 'sca', { id: 's1', countedIn: 'c1' }),
      other(city({ fms_id: 's2', budget: 30 }), 'sca', { id: 's2' }), other(city({ fms_id: 'm1', budget: 900 }), 'mta', { id: 'm1', status: 'completed' })]
    const t = programTotals(ps)
    expect(t.map((x) => [x.id, x.projects, x.budget])).toEqual([['nyc_capital', 1, 100], ['sca', 1, 30], ['mta', 0, 0]])
  })

  it('picks each program\'s largest single-site Tier A project for the ground view', () => {
    const ps = [city({ fms_id: 'big', budget: 900 }), city({ fms_id: 'small', budget: 10 }), city({ fms_id: 'b', tier: 'B', budget: 5000 })]
    const sites = new Map([['big', [site(301), site(302)]], ['small', [site(301)]]])
    expect(largestPlaced(ps, sites).map((s) => s.id)).toEqual(['small'])
  })

  it('counts district money where the work is and where it serves, per resident', () => {
    const ps = [city({ fms_id: 'j', budget: 1000 })]
    const sites = new Map([['j', [site(101)]]])
    const counts = { j: [['district', '101', 0.25, 'site', null], ['district', '102', 0.25, 'site', null], ['citywide', null, 0.5, 'citywide', null]] as never }
    const pop = [{ level: 'district', area: '101', population: 10 }, { level: 'district', area: '102', population: 40 }, { level: 'citywide', area: null, population: 100 }]
    const dm = districtMoney(ps, sites, counts, pop, new Map([['101', 'Financial District-Tribeca']]))
    const r101 = dm.rows.find((r) => r.district === '101')!
    expect([r101.name, r101.where, r101.serves]).toEqual(['Financial District-Tribeca', 1000, 250])
    expect(dm.citywidePerResident).toBe(5)
    expect(leadProjectIn('101', ps, sites)?.id).toBe('j')
  })

  it('follows a mega project through its lines, sites and series', () => {
    const line = (id: string, extra: Record<string, unknown>) => other(city({ fms_id: id, budget: 10 }), 'mta', { id, extra })
    const ps = [line('m1', { megaProject: 'Penn Station Access', forecastMonth: '2027-03', pctComplete: 55 }),
      other(line('m2', { megaProject: 'Penn Station Access', forecastMonth: '2030-12' }), 'mta', { budget: 30 }), line('m3', { megaProject: 'Other' })]
    const sites = new Map([['m1', [site(202), { ...site(209), lon: -73.8 }]], ['m2', [site(202)]]])
    const story = megaProject('Penn Station Access', ps, sites, [{ mega_project: 'Penn Station Access', load: '2020-03-31', total: 5 }])
    expect([story.lines.length, story.stations.length, story.budget]).toEqual([2, 2, 40])
    // Each line keeps its own date: the latest finish is not paired with another line's original.
    expect(story.work.map((w) => [w.id, w.finish, w.pctComplete])).toEqual([['m2', '2030-12', null], ['m1', '2027-03', 55]])
  })

  it('sets the borough-based jails against their original budgets', () => {
    const ps = [city({ fms_id: 'BBJ-M', budget: 4300, original_budget: 2200, original_period: 202110 }),
      city({ fms_id: 'BBJ-K', budget: 3300, original_budget: 2000, original_period: 202110 }),
      city({ fms_id: 'BBJ-QGAR', budget: 95, status: 'dropped' }), city({ fms_id: 'BBJCCM', budget: 19 })]
    expect(boroughJails(ps)).toEqual({ projects: 2, budget: 7600, original: 4200, originalPeriod: 202110 })
  })
})

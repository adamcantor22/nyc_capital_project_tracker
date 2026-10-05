import { describe, expect, it } from 'vitest'
import { toProject, type ScaRow } from '../data/programs/sca'
import { countable, measureById, total } from './registry'

const row = (o: Partial<ScaRow>): ScaRow => ({
  program: 'sca', id: 'sca:DSF1|K250', dsf: 'DSF1', building: 'K250', school_name: 'P.S. 250 - BROOKLYN', school_district: '14',
  project_types: 'SCA CIP', description: 'DCAS ELECTRIFICATION', n_phases: 4, status: 'current', sca_status: 'active',
  current_phase: 'Construction', phase_group: 'Active', theme: 'Education', start_date: '2025-04-10', forecast_end: null,
  finished: null, budget: 45, spend: 5, spend_pct: 11.1, program_figure: null, city_fms_id: null, city_link: null,
  borough: 'Brooklyn', tier: 'A', source: 'sca_active', lon: -73.9, lat: 40.7, matched_to: null,
  location_evidence: '8586-3zfm, SCA Active Projects Under Construction', on_map: true, approximate: false,
  district: 301, districts: [301], neighborhood: null, ...o,
})

describe('SCA adapter', () => {
  it('maps a row onto the common fields, with its report month and city link', () => {
    const p = toProject(row({ city_fms_id: 'SCAELK250' }), '2026-08-04')
    expect([p.program, p.agencies, p.lastReported, p.countedIn, p.extra.fmsTitle]).toEqual(['sca', ['SCA'], 202608, 'SCAELK250', 'P.S. 250 - BROOKLYN'])
    expect(toProject(row({ sca_status: 'complete', phase_group: 'Done', finished: '2024-01-02' })).phase).toBe('Completed')
  })
})

describe('countable', () => {
  const city = { ...toProject(row({})), id: 'SCAELK250', program: 'nyc_capital', budget: 62 }
  const linked = toProject(row({ id: 'sca:linked', city_fms_id: 'SCAELK250' }))
  const other = toProject(row({ id: 'sca:other', budget: 10 }))
  const budget = measureById.budget

  it('counts work funded through a city FMS ID once when both are in the set', () => {
    expect(total(countable([city, linked, other]), budget)).toBe(72)
  })
  it('counts the SCA project when its city record is not in the set', () => {
    expect(total(countable([linked, other]), budget)).toBe(55)
  })
})

describe('MTA adapter', () => {
  it('maps months to days, keeps spend unpublished and the reserve flag', async () => {
    const { toProject } = await import('../data/programs/mta')
    const p = toProject({
      program: 'mta', id: 'mta:T8041237', acep: 'T8041237', capital_plan: 'Capital Plan 2020 - 2024', agency: 'New York City Transit',
      category: null, element: null, description: 'Platform Screen Doors Pilot', scope: null, mega_project: null, phase: 'Design',
      phase_group: 'Active', status: 'current', mta_status: 'live', theme: 'Transportation', subtheme: 'Transit (MTA)',
      spending_kind: 'physical', mta_calls_reserve: false, budget: 256199068, original_budget: 256199068, budget_vs_original: 0,
      pct_complete: 0, current_start: '2023-01', forecast_completion: '2029', original_completion: null, first_load: '2023-03-31',
      last_load: '2026-03-31', borough: null, tier: 'Unplaced', source: 'dollar', lon: null, lat: null, n_sites: 0,
      location_evidence: 'wcsa-vkhf has no point', on_map: false, approximate: false, outside_nyc: null, district: null, districts: [],
      neighborhood: null,
    })
    expect([p.startDate, p.forecastCompletion, p.lastReported, p.spend, p.spendPct]).toEqual(['2023-01-01', '2029-12-31', 202603, 0, null])
  })
})

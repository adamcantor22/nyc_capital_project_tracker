import type { Project, ProgramAdapter, Tier } from '../types'

/** One row of sca_projects.json (pipeline/export.py). */
export interface ScaRow {
  program: string
  id: string
  dsf: string | null
  building: string
  school_name: string | null
  school_district: string | null
  project_types: string
  description: string | null
  n_phases: number
  status: 'current'
  sca_status: 'complete' | 'active' | 'not_started'
  current_phase: string | null
  phase_group: string
  theme: string
  start_date: string | null
  forecast_end: string | null
  finished: string | null
  budget: number
  spend: number
  spend_pct: number | null
  program_figure: number | null
  city_fms_id: string | null
  city_link: string | null
  borough: string | null
  tier: Tier
  source: string
  lon: number | null
  lat: number | null
  matched_to: string | null
  location_evidence: string
  on_map: boolean
  approximate: boolean
  district: number | null
  districts: number[]
  neighborhood: string | null
}

/** '2026-08-04' -> 202608, so SCA rows sort with the city's report periods. */
const period = (day: string | undefined) => (day ? Number(day.slice(0, 4) + day.slice(5, 7)) : 0)

export function toProject(r: ScaRow, updated?: string): Project {
  const reported = period(updated)
  return {
    id: r.id,
    program: r.program,
    title: r.description || r.project_types,
    agencies: ['SCA'],
    sponsor: null,
    borough: r.borough,
    district: r.district,
    districts: r.districts,
    neighborhood: r.neighborhood,
    theme: r.theme,
    subtheme: null,
    phase: r.sca_status === 'complete' ? 'Completed' : r.current_phase,
    phaseGroup: r.phase_group,
    status: r.status,
    budget: r.budget,
    spend: r.spend,
    spendPct: r.spend_pct,
    budgetChange: null,
    budgetCity: null,
    budgetNonCity: null,
    budgetFederal: null,
    budgetState: null,
    budgetOther: null,
    startDate: r.start_date,
    forecastCompletion: r.finished ?? r.forecast_end,
    milestones: { designStart: null, designEnd: null, constructionStart: null, constructionEnd: r.finished, phaseStart: null },
    hasSchedule: false,
    firstReported: reported,
    lastReported: reported,
    tier: r.tier,
    lon: r.lon,
    lat: r.lat,
    onMap: r.on_map,
    approximate: r.approximate,
    matchedTo: r.matched_to,
    sourceFlag: null,
    outsideNyc: null,
    countedIn: r.city_fms_id,
    extra: {
      fmsTitle: r.school_name,
      source: r.source,
      building: r.building,
      dsf: r.dsf,
      schoolDistrict: r.school_district,
      projectTypes: r.project_types,
      nPhases: r.n_phases,
      programFigure: r.program_figure,
      cityLink: r.city_link,
      locationEvidence: r.location_evidence,
    },
  }
}

export const sca: ProgramAdapter = {
  id: 'sca',
  async load(entry, fetchJson) {
    const rows = await fetchJson<ScaRow[]>(entry.files.projects)
    return rows.map((r) => toProject(r, entry.updated))
  },
}

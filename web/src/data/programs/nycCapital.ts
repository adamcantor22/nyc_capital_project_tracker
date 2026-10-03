import type { Project, ProgramAdapter, Tier } from '../types'

/** One row of projects.json (pipeline/export.py, schema v2). */
export interface NycCapitalRow {
  program: string
  fms_id: string
  title: string | null
  agency_project_name: string | null
  description: string | null
  managing_agencies: string[]
  sponsor_agency: string | null
  pids: number[]
  borough: string | null
  community_board: string | null
  category: string | null
  budget_line: string | null
  theme: string
  subtheme: string | null
  phase: string | null
  phase_group: string
  has_schedule: boolean
  forecast_completion: string | null
  budget: number
  budget_city: number | null
  budget_non_city: number | null
  budget_federal?: number | null
  budget_state?: number | null
  budget_other?: number | null
  start_date?: string | null
  spend: number
  spend_pct: number | null
  budget_change: number | null
  first_reported: number
  last_reported: number
  status: 'current' | 'dropped'
  tier: Tier
  source: string | null
  lon: number | null
  lat: number | null
  matched_to: string | null
  source_flag: string | null
  spread_m: number | null
  n_points: number | null
  on_map: boolean
  approximate: boolean
  outside_nyc: 'near' | 'far' | null
  district: number | null
  districts: number[]
  neighborhood: string | null
}

export function toProject(r: NycCapitalRow): Project {
  return {
    id: r.fms_id,
    program: r.program,
    title: r.agency_project_name || r.title || r.fms_id,
    agencies: r.managing_agencies,
    sponsor: r.sponsor_agency,
    borough: r.borough,
    district: r.district,
    districts: r.districts,
    neighborhood: r.neighborhood,
    theme: r.theme,
    subtheme: r.subtheme,
    phase: r.phase,
    phaseGroup: r.phase_group,
    status: r.status,
    budget: r.budget,
    spend: r.spend,
    spendPct: r.spend_pct,
    budgetChange: r.budget_change,
    budgetCity: r.budget_city,
    budgetNonCity: r.budget_non_city,
    budgetFederal: r.budget_federal ?? null,
    budgetState: r.budget_state ?? null,
    budgetOther: r.budget_other ?? null,
    startDate: r.start_date ?? null,
    forecastCompletion: r.forecast_completion,
    hasSchedule: r.has_schedule,
    firstReported: r.first_reported,
    lastReported: r.last_reported,
    tier: r.tier,
    lon: r.lon,
    lat: r.lat,
    onMap: r.on_map,
    approximate: r.approximate,
    matchedTo: r.matched_to,
    sourceFlag: r.source_flag,
    outsideNyc: r.outside_nyc,
    extra: {
      fmsTitle: r.title,
      description: r.description,
      pids: r.pids,
      communityBoard: r.community_board,
      category: r.category,
      budgetLine: r.budget_line,
      source: r.source,
      spreadM: r.spread_m,
      nPoints: r.n_points,
    },
  }
}

export const nycCapital: ProgramAdapter = {
  id: 'nyc_capital',
  async load(entry, fetchJson) {
    const rows = await fetchJson<NycCapitalRow[]>(entry.files.projects)
    return rows.map(toProject)
  },
}

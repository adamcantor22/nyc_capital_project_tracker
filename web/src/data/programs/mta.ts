import type { Project, ProgramAdapter, Tier } from '../types'

/** One row of mta_projects.json (pipeline/export.py). */
export interface MtaRow {
  program: string
  id: string
  acep: string
  capital_plan: string
  agency: string
  category: string | null
  element: string | null
  description: string | null
  scope: string | null
  mega_project: string | null
  phase: string | null
  phase_group: string
  status: 'current' | 'dropped'
  mta_status: string
  theme: string
  subtheme: string | null
  spending_kind: string | null
  mta_calls_reserve: boolean
  budget: number | null
  original_budget: number | null
  budget_vs_original: number | null
  pct_complete: number | null
  current_start: string | null
  forecast_completion: string | null
  has_schedule?: boolean
  original_completion: string | null
  first_load: string
  last_load: string
  borough: string | null
  tier: Tier
  source: string
  lon: number | null
  lat: number | null
  n_sites: number
  location_evidence: string
  on_map: boolean
  approximate: boolean
  outside_nyc: 'near' | 'far' | null
  district: number | null
  districts: number[]
  neighborhood: string | null
}

/** '2026-03-31' -> 202603, so MTA loads sort with the city's report periods. */
const period = (day: string) => Number(day.slice(0, 4) + day.slice(5, 7))
/** MTA dates are months ('2029-10') or years ('2029'); the site's dates are days. */
const day = (m: string | null) => (m ? (m.length === 4 ? `${m}-12-31` : `${m}-01`) : null)

export function toProject(r: MtaRow): Project {
  return {
    id: r.id,
    program: r.program,
    title: r.description || r.acep,
    agencies: [r.agency],
    sponsor: null,
    borough: r.borough,
    district: r.district,
    districts: r.districts,
    neighborhood: r.neighborhood,
    theme: r.theme,
    subtheme: r.subtheme,
    phase: r.phase,
    phaseGroup: r.phase_group,
    status: r.status,
    budget: r.budget ?? 0,
    spend: 0,
    spendPct: null,
    budgetChange: null,
    budgetCity: null,
    budgetNonCity: null,
    budgetFederal: null,
    budgetState: null,
    budgetOther: null,
    startDate: day(r.current_start),
    forecastCompletion: day(r.forecast_completion),
    milestones: { designStart: null, designEnd: null, constructionStart: null, constructionEnd: null, phaseStart: null },
    hasSchedule: r.has_schedule ?? !!r.forecast_completion,
    firstReported: period(r.first_load),
    lastReported: period(r.last_load),
    tier: r.tier,
    lon: r.lon,
    lat: r.lat,
    onMap: r.on_map,
    approximate: r.approximate,
    matchedTo: null,
    sourceFlag: null,
    outsideNyc: r.outside_nyc,
    countedIn: null,
    extra: {
      acep: r.acep,
      capitalPlan: r.capital_plan,
      description: r.scope,
      megaProject: r.mega_project,
      spendingKind: r.spending_kind,
      callsReserve: r.mta_calls_reserve,
      originalBudget: r.original_budget,
      pctComplete: r.pct_complete,
      forecastMonth: r.forecast_completion,
      originalCompletion: r.original_completion,
      source: r.source,
      nSites: r.n_sites,
      locationEvidence: r.location_evidence,
    },
  }
}

export const mta: ProgramAdapter = {
  id: 'mta',
  async load(entry, fetchJson) {
    const rows = await fetchJson<MtaRow[]>(entry.files.projects)
    return rows.map(toProject)
  },
}

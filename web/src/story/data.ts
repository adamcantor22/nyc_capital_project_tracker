import type { Site } from '../areas/aggregate'
import type { Project, Tier } from '../data/types'
import type { AreaCount } from './plates'

/** One row of story_projects.json (pipeline/export.py story_projects()): only the fields the story reads. */
export interface StoryRow {
  id: string
  program: string
  status: Project['status']
  tier: Tier
  on_map: boolean
  lon?: number
  lat?: number
  budget: number
  spend: number
  title?: string
  theme?: string
  subtheme?: string
  borough?: string
  district?: number
  neighborhood?: string
  counted_in?: string
  mega_project?: string
  pct_complete?: number
  forecast?: string
  original_budget?: number
  original_period?: number
  /** [lon, lat, share, district, neighborhood] per site. */
  sites?: [number, number, number, number | null, string | null][]
  counts?: AreaCount[]
}

/** A story row as a Project, the fields the story does not read left empty. */
export function toStoryProject(r: StoryRow): Project {
  return {
    id: r.id, program: r.program, title: r.title ?? r.id, agencies: [], sponsor: null, borough: r.borough ?? null,
    district: r.district ?? null, districts: [], neighborhood: r.neighborhood ?? null, theme: r.theme ?? '',
    subtheme: r.subtheme ?? null, phase: null, phaseGroup: '', status: r.status, budget: r.budget, spend: r.spend,
    spendPct: null, budgetChange: null, budgetCity: null, budgetNonCity: null, budgetFederal: null, budgetState: null,
    budgetOther: null, startDate: null, forecastCompletion: null,
    milestones: { designStart: null, designEnd: null, constructionStart: null, constructionEnd: null, phaseStart: null },
    hasSchedule: false, firstReported: 0, lastReported: 0, tier: r.tier, lon: r.lon ?? null, lat: r.lat ?? null,
    onMap: r.on_map, approximate: r.tier === 'B', matchedTo: null, sourceFlag: null, outsideNyc: null,
    countedIn: r.counted_in ?? null,
    extra: {
      megaProject: r.mega_project ?? null, pctComplete: r.pct_complete ?? null, forecastMonth: r.forecast ?? null,
      originalBudget: r.original_budget ?? null, originalPeriod: r.original_period ?? null,
    },
  }
}

export function fromStoryRows(rows: StoryRow[]): { projects: Project[]; sites: Map<string, Site[]>; counts: Record<string, AreaCount[]> } {
  const sites = new Map<string, Site[]>()
  const counts: Record<string, AreaCount[]> = {}
  for (const r of rows) {
    if (r.sites) sites.set(r.id, r.sites.map(([lon, lat, share, district, nta]) => ({ lon, lat, share, share_method: 'equal', district, nta })))
    if (r.counts) counts[r.id] = r.counts
  }
  return { projects: rows.map(toStoryProject), sites, counts }
}

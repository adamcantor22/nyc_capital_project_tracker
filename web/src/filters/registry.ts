import type { Project } from '../data/types'

export type FilterValue = string[]
export type FilterState = Record<string, FilterValue>

export interface FilterDef {
  id: string
  label: string
  /** The project's value(s) for this filter; a project matches when any value is selected. */
  values(p: Project): string[]
  /** Fixed option order; otherwise options are sorted by project count. */
  order?: string[]
}

const one = (v: string | null | undefined) => (v ? [v] : [])

export const TIER_ORDER = ['A', 'B', 'C', 'D', 'E', 'Unplaced']
export const BUDGET_BANDS = ['Under $1M', '$1M–$10M', '$10M–$100M', '$100M–$1B', '$1B and up']

export function budgetBand(b: number): string {
  if (b < 1e6) return BUDGET_BANDS[0]
  if (b < 1e7) return BUDGET_BANDS[1]
  if (b < 1e8) return BUDGET_BANDS[2]
  if (b < 1e9) return BUDGET_BANDS[3]
  return BUDGET_BANDS[4]
}

/** Adding a filter: one entry here. The filter bar, URL state and counts follow. */
export const filters: FilterDef[] = [
  { id: 'status', label: 'Status', values: (p) => [p.status], order: ['current', 'dropped'] },
  { id: 'theme', label: 'Theme', values: (p) => one(p.theme) },
  { id: 'phase', label: 'Phase', values: (p) => one(p.phaseGroup) },
  { id: 'agency', label: 'Managing agency', values: (p) => p.agencies },
  { id: 'sponsor', label: 'Sponsor agency', values: (p) => one(p.sponsor) },
  { id: 'borough', label: 'Borough', values: (p) => one(p.borough) },
  { id: 'district', label: 'Community district', values: (p) => p.districts.map(String) },
  { id: 'tier', label: 'Location precision', values: (p) => [p.tier], order: TIER_ORDER },
  { id: 'size', label: 'Budget', values: (p) => [budgetBand(p.budget)], order: BUDGET_BANDS },
  { id: 'schedule', label: 'Has a schedule', values: (p) => [p.hasSchedule ? 'yes' : 'no'], order: ['yes', 'no'] },
  { id: 'program', label: 'Program', values: (p) => [p.program] },
]

export const filterById = Object.fromEntries(filters.map((f) => [f.id, f]))

export function matches(p: Project, state: FilterState, skip?: string): boolean {
  for (const [id, selected] of Object.entries(state)) {
    if (id === skip || !selected.length) continue
    const def = filterById[id]
    if (def && !def.values(p).some((v) => selected.includes(v))) return false
  }
  return true
}

export function applyFilters(projects: Project[], state: FilterState): Project[] {
  return projects.filter((p) => matches(p, state))
}

/** Option counts for one filter, under every other active filter (so options never dead-end). */
export function optionCounts(projects: Project[], state: FilterState, id: string): [string, number][] {
  const def = filterById[id]
  const counts = new Map<string, number>()
  for (const p of projects) {
    if (!matches(p, state, id)) continue
    for (const v of def.values(p)) counts.set(v, (counts.get(v) ?? 0) + 1)
  }
  const entries = [...counts]
  if (def.order) {
    const rank = (v: string) => (def.order!.indexOf(v) + 1 || 999)
    return entries.sort((a, b) => rank(a[0]) - rank(b[0]))
  }
  return entries.sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
}

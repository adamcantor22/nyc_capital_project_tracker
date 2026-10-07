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
  /** Filters sharing a group are ORed (theme and subtheme: a whole theme, or some of its subthemes). */
  group?: string
}

const one = (v: string | null | undefined) => (v ? [v] : [])

/** A project's subtheme key; projects without one get 'Other <theme>' so a theme can be split in full. */
export const subKey = (p: Project) => p.subtheme ?? `Other ${p.theme.toLowerCase()}`

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
  { id: 'status', label: 'Status', values: (p) => [p.status], order: ['current', 'completed', 'dropped'] },
  { id: 'theme', label: 'Theme', values: (p) => one(p.theme), group: 'theme' },
  { id: 'subtheme', label: 'Subtheme', values: (p) => [subKey(p)], group: 'theme' },
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

const hit = (p: Project, state: FilterState, id: string) => {
  const sel = state[id]
  return !!sel?.length && filterById[id].values(p).some((v) => sel.includes(v))
}

/** `skip` leaves out a filter (and the rest of its group), for option counts. */
export function matches(p: Project, state: FilterState, skip?: string): boolean {
  const skipGroup = skip ? filterById[skip]?.group : undefined
  const groups = new Map<string, string[]>()
  for (const [id, selected] of Object.entries(state)) {
    const def = filterById[id]
    if (!def || id === skip || !selected.length) continue
    if (def.group) {
      if (def.group !== skipGroup) groups.set(def.group, [...(groups.get(def.group) ?? []), id])
    } else if (!hit(p, state, id)) return false
  }
  for (const ids of groups.values()) if (!ids.some((id) => hit(p, state, id))) return false
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

/** Legend taps: a plain tap shows only `values` (tapping the current only-selection clears it);
 * `add` (long-press, Shift or Ctrl/Cmd-click) toggles `values` within the selection. */
export function pick(list: string[] = [], values: string[], add: boolean): string[] {
  if (add) {
    const allOn = values.every((v) => list.includes(v))
    return allOn ? list.filter((v) => !values.includes(v)) : [...new Set([...list, ...values])]
  }
  const same = list.length === values.length && values.every((v) => list.includes(v))
  return same ? [] : [...values]
}

/** Theme keys (tap = only these themes, add = toggle them whole). Their subtheme picks are dropped either way. */
export function pickTheme(f: FilterState, themes: string[], add: boolean, subsOf: (t: string) => string[]): FilterState {
  const theirs = new Set(themes.flatMap(subsOf))
  const subs = (f.subtheme ?? []).filter((s) => !theirs.has(s))
  if (add) return { ...f, theme: pick(f.theme, themes, true), subtheme: subs }
  const only = !(f.subtheme ?? []).length && pick(f.theme, themes, false).length === 0
  return { ...f, theme: only ? [] : [...themes], subtheme: [] }
}

/** Subtheme keys, as a tree of checkboxes: a theme is either whole (in `theme`) or split (some of its
 * subthemes in `subtheme`), never both. Tap = only this subtheme; add = toggle it within its theme. */
export function pickSub(f: FilterState, theme: string, sub: string, siblings: string[], add: boolean): FilterState {
  const th = f.theme ?? []
  const su = f.subtheme ?? []
  if (!add) {
    const only = !th.length && su.length === 1 && su[0] === sub
    return { ...f, theme: only ? [theme] : [], subtheme: only ? [] : [sub] }
  }
  if (th.includes(theme)) return { ...f, theme: th.filter((t) => t !== theme), subtheme: [...su, ...siblings.filter((s) => s !== sub)] }
  if (su.includes(sub)) return { ...f, subtheme: su.filter((s) => s !== sub) }
  const next = [...su, sub]
  if (siblings.every((s) => next.includes(s))) return { ...f, theme: [...th, theme], subtheme: next.filter((s) => !siblings.includes(s)) }
  return { ...f, subtheme: next }
}

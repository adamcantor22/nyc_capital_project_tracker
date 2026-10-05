import type { Project } from '../data/types'

export interface Measure {
  id: string
  label: string
  value(p: Project): number | null
  /** Signed measures show + for increases. */
  signed?: boolean
}

/** Adding a money measure (a funding source, a new program's amount): one entry here. */
export const measures: Measure[] = [
  { id: 'budget', label: 'Budget', value: (p) => p.budget },
  { id: 'spend', label: 'Spent to date', value: (p) => p.spend },
  { id: 'city', label: 'City funds', value: (p) => p.budgetCity },
  { id: 'non_city', label: 'Non-city funds', value: (p) => p.budgetNonCity },
  { id: 'federal', label: 'Federal funds (estimated)', value: (p) => p.budgetFederal },
  { id: 'state', label: 'State funds (estimated)', value: (p) => p.budgetState },
  { id: 'other_noncity', label: 'Other non-city funds (estimated)', value: (p) => p.budgetOther },
  { id: 'change', label: 'Budget change since last report', value: (p) => p.budgetChange, signed: true },
]

export const measureById = Object.fromEntries(measures.map((m) => [m.id, m]))

/** The projects whose amounts count in a total: an SCA project funded through a city FMS ID is left out
 * when that city record is in the same set, so the work is counted once (pipeline/sca_city_links.csv). */
export function countable(projects: Project[]): Project[] {
  if (!projects.some((p) => p.countedIn)) return projects
  const ids = new Set(projects.map((p) => p.id))
  return projects.filter((p) => !p.countedIn || !ids.has(p.countedIn))
}

export function total(projects: Project[], m: Measure): number {
  let s = 0
  for (const p of projects) s += m.value(p) ?? 0
  return s
}

const compact = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', notation: 'compact', maximumFractionDigits: 1 })

export function money(v: number | null, signed = false): string {
  if (v === null) return '—'
  const s = compact.format(Math.abs(v))
  if (!signed) return v < 0 ? `−${s}` : s
  return v > 0 ? `+${s}` : v < 0 ? `−${s}` : s
}

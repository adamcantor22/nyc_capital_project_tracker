import type { Project } from '../data/types'

export interface Summary {
  n: number
  budget: number
  spend: number
  change: number
  changed: number
  nonCity: number
  approximate: number
  byTheme: [string, number][]
  byPhase: [string, number][]
}

/** Totals for a set of projects. Budgets are already per FMS ID (deduplicated in the export). */
/** weights: share of each project counted (multi-site projects split across areas); 1 when absent. */
export function summarize(ps: Project[], weights?: Map<string, number>): Summary {
  const theme = new Map<string, number>()
  const phase = new Map<string, number>()
  let budget = 0, spend = 0, change = 0, changed = 0, nonCity = 0, approximate = 0
  for (const p of ps) {
    const w = weights?.get(p.id) ?? 1
    budget += p.budget * w
    spend += p.spend * w
    if (p.budgetChange) {
      change += p.budgetChange * w
      changed += 1
    }
    nonCity += (p.budgetNonCity ?? 0) * w
    if (p.approximate) approximate += 1
    theme.set(p.theme, (theme.get(p.theme) ?? 0) + p.budget * w)
    phase.set(p.phaseGroup, (phase.get(p.phaseGroup) ?? 0) + 1)
  }
  const desc = (m: Map<string, number>) => [...m].sort((a, b) => b[1] - a[1])
  return { n: ps.length, budget, spend, change, changed, nonCity, approximate, byTheme: desc(theme), byPhase: desc(phase) }
}

export interface Box { w: number; s: number; e: number; n: number }

/** Pinned projects inside a box. Area totals count only point-level locations (Tier A, and B labelled
 * approximate); district- and borough-level projects have no real point to fall inside a box. */
export function inBox(ps: Project[], b: Box): Project[] {
  return ps.filter((p) => p.onMap && p.lon! >= b.w && p.lon! <= b.e && p.lat! >= b.s && p.lat! <= b.n)
}

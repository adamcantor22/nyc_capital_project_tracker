import type { Project } from '../data/types'

export type Level = 'neighborhoods' | 'districts' | 'boroughs'
export interface Site {
  fms_id: string
  lon: number
  lat: number
  share: number
  share_method: 'single' | 'equal' | 'source_proportion'
  district: number | null
  nta: string | null
}

export interface AreaStat {
  n: number
  budget: number
  spend: number
  nonCity: number
  federal: number
  state: number
  change: number
  /** Project id -> share of its budget counted here (1 unless split across sites). */
  weights: Map<string, number>
}

/** Which projects count at each level: located at least as precisely as the area (docs/ui-plan.md).
 * Boroughs take every project with a borough; districts take point-level and district-level projects
 * (A, B, C, D) by their sites; neighborhoods take A, B and C by their sites. */
const ELIGIBLE: Record<Level, (p: Project) => boolean> = {
  boroughs: (p) => !!p.borough && p.tier !== 'Unplaced',
  districts: (p) => ['A', 'B', 'C', 'D'].includes(p.tier),
  neighborhoods: (p) => ['A', 'B', 'C'].includes(p.tier),
}

export function aggregateAreas(level: Level, projects: Project[], sites: Map<string, Site[]>): Map<string, AreaStat> {
  const out = new Map<string, AreaStat>()
  const add = (key: string | null, p: Project, w: number) => {
    if (!key || w <= 0) return
    let a = out.get(key)
    if (!a) out.set(key, (a = { n: 0, budget: 0, spend: 0, nonCity: 0, federal: 0, state: 0, change: 0, weights: new Map() }))
    if (!a.weights.has(p.id)) a.n += 1
    a.weights.set(p.id, (a.weights.get(p.id) ?? 0) + w)
    a.budget += p.budget * w
    a.spend += p.spend * w
    a.nonCity += (p.budgetNonCity ?? 0) * w
    a.federal += (p.budgetFederal ?? 0) * w
    a.state += (p.budgetState ?? 0) * w
    a.change += (p.budgetChange ?? 0) * w
  }
  for (const p of projects) {
    if (!ELIGIBLE[level](p)) continue
    if (level === 'boroughs') {
      add(p.borough, p, 1)
      continue
    }
    // Multi-site projects split by site share, so each area gets its part of the budget.
    for (const s of sites.get(p.id) ?? []) add(level === 'districts' ? (s.district?.toString() ?? null) : s.nta, p, s.share)
  }
  return out
}

export interface AreaMeasure {
  id: string
  label: string
  value(a: AreaStat): number | null
  /** seq: one hue light to dark; div: blue (decrease) through grey to red (increase). */
  kind: 'seq' | 'div'
  format(v: number): string
}

import { aggregateAreas, type Site } from '../areas/aggregate'
import type { Project } from '../data/types'
import { countable } from '../measures/registry'

/** The three builders, in the order the story names them, with the tint each wears on the story map. */
export const PROGRAMS = [
  { id: 'nyc_capital', label: 'The city', short: 'City', tint: '#2f6fb5' },
  { id: 'sca', label: 'School Construction Authority', short: 'Schools', tint: '#c9780f' },
  { id: 'mta', label: 'MTA', short: 'MTA', tint: '#2e8b62' },
] as const
export type ProgramId = (typeof PROGRAMS)[number]['id']
/** Sequential ramp for money per resident: one hue, light to dark (the dataviz reference's blue steps). */
export const RAMP = ['#e3eefc', '#b7d3f6', '#86b6ef', '#5598e7', '#2a78d6', '#1c5cab', '#104281']
export const tintOf = (program: string) => PROGRAMS.find((p) => p.id === program)?.tint ?? '#7b8494'

export interface ProgramTotal { id: ProgramId; label: string; projects: number; budget: number }

/** Unfinished work per program; SCA work that a city record already counts is counted once, as the city's. */
export function programTotals(projects: Project[]): ProgramTotal[] {
  const current = countable(projects.filter((p) => p.status === 'current'))
  return PROGRAMS.map(({ id, label }) => {
    const ps = current.filter((p) => p.program === id)
    return { id, label, projects: ps.length, budget: ps.reduce((s, p) => s + p.budget, 0) }
  })
}

export interface Spot { id: string; program: string; title: string; budget: number; lon: number; lat: number; place: string | null; note?: string }

/** Each program's largest unfinished project placed at one official point (Tier A, a single site), so the map
 * can go to it: the ground-level counterpart of the program's total. */
export function largestPlaced(projects: Project[], sites: Map<string, Site[]>): Spot[] {
  const out: Spot[] = []
  for (const { id } of PROGRAMS) {
    const best = projects
      .filter((p) => p.program === id && p.status === 'current' && p.tier === 'A' && p.lon !== null && p.lat !== null
        && (sites.get(p.id)?.length ?? 1) === 1)
      .sort((a, b) => b.budget - a.budget)[0]
    if (best) out.push(spot(best))
  }
  return out
}

export const spot = (p: Project): Spot => ({ id: p.id, program: p.program, title: p.title, budget: p.budget, lon: p.lon!, lat: p.lat!, place: p.neighborhood ?? p.borough })

/** One row of area_counts.json: where a project's money counts by the area it serves (pipeline/project_areas.py). */
export type AreaCount = [level: string, area: string | null, share: number, method: string, nta: string | null]
export interface PopulationRow { level: string; area: string | null; population: number }

export interface DistrictRow {
  district: string
  name: string
  population: number
  /** Money counted where the work is: sites at least district-precise (Tiers A-D), by site share. */
  where: number
  /** Money counted in the district the work serves (an estimate: area-served classes). */
  serves: number
}

/** City money per district, counted two ways (Per resident plate). */
export function districtMoney(projects: Project[], sites: Map<string, Site[]>, counts: Record<string, AreaCount[]>,
  population: PopulationRow[], names: Map<string, string>): { rows: DistrictRow[]; citywidePerResident: number; cityPopulation: number } {
  const city = projects.filter((p) => p.program === 'nyc_capital' && p.status === 'current')
  const where = aggregateAreas('districts', city, sites)
  const serves = new Map<string, number>()
  let citywide = 0
  for (const p of city) {
    for (const [level, area, share] of counts[p.id] ?? []) {
      if (level === 'district' && area) serves.set(area, (serves.get(area) ?? 0) + p.budget * share)
      if (level === 'citywide') citywide += p.budget * share
    }
  }
  const pop = new Map(population.filter((r) => r.level === 'district').map((r) => [r.area!, r.population]))
  const cityPopulation = population.find((r) => r.level === 'citywide')?.population ?? 0
  const rows = [...pop.entries()].map(([district, population]) => ({
    district, population, name: names.get(district) ?? district,
    where: where.get(district)?.budget ?? 0, serves: serves.get(district) ?? 0,
  }))
  return { rows, citywidePerResident: cityPopulation ? citywide / cityPopulation : 0, cityPopulation }
}

/** The largest project with a site in each district, by the share of its money there. */
export function leadProjectIn(district: string, projects: Project[], sites: Map<string, Site[]>): Spot | null {
  let best: { p: Project; s: Site; v: number } | null = null
  for (const p of projects) {
    if (p.program !== 'nyc_capital' || p.status !== 'current' || !['A', 'B', 'C', 'D'].includes(p.tier)) continue
    for (const s of sites.get(p.id) ?? []) {
      if (String(s.district) !== district) continue
      const v = p.budget * s.share
      if (!best || v > best.v) best = { p, s, v }
    }
  }
  return best ? { ...spot(best.p), lon: best.s.lon, lat: best.s.lat, budget: best.v, place: best.s.nta ?? best.p.borough } : null
}

export interface MegaPoint { mega_project: string; load: string; total: number }

export interface ProjectLine { id: string; title: string; budget: number; pctComplete: number | null; finish: string | null }

export interface ProjectStory {
  name: string
  lines: Project[]
  budget: number
  series: { load: string; total: number }[]
  stations: { lon: number; lat: number; place: string | null }[]
  /** Unfinished budget lines with money, largest first, each with the dashboard's completion (YYYY-MM or YYYY). */
  work: ProjectLine[]
}

/** Everything the project-led plate shows for one MTA mega project. */
export function megaProject(name: string, projects: Project[], sites: Map<string, Site[]>, series: MegaPoint[]): ProjectStory {
  const lines = projects.filter((p) => p.program === 'mta' && p.extra.megaProject === name && p.status !== 'dropped')
  const seen = new Set<string>()
  const stations: ProjectStory['stations'] = []
  for (const p of lines) {
    for (const s of sites.get(p.id) ?? []) {
      const k = `${s.lon.toFixed(4)},${s.lat.toFixed(4)}`
      if (!seen.has(k)) { seen.add(k); stations.push({ lon: s.lon, lat: s.lat, place: s.nta }) }
    }
  }
  const work = lines.filter((p) => p.status === 'current' && p.budget > 0).sort((a, b) => b.budget - a.budget).map((p) => ({
    id: p.id, title: p.title, budget: p.budget,
    pctComplete: (p.extra.pctComplete as number | null) ?? null, finish: (p.extra.forecastMonth as string | null) ?? null,
  }))
  return {
    name, lines, stations, work,
    budget: lines.filter((p) => p.status === 'current').reduce((s, p) => s + p.budget, 0),
    series: series.filter((r) => r.mega_project === name).map(({ load, total }) => ({ load, total })),
  }
}

export interface JailsStory { projects: number; budget: number; original: number; originalPeriod: number | null }

/** The four borough-based jails (DDC's BBJ-K, -M, -Q, -X design-build records): money now against each record's
 * original budget (budget_original, from qj5n-h5qp). */
export function boroughJails(projects: Project[]): JailsStory {
  const ps = projects.filter((p) => p.program === 'nyc_capital' && p.status === 'current' && p.id.startsWith('BBJ-'))
  const periods = ps.map((p) => p.extra.originalPeriod as number | null).filter((x): x is number => x !== null)
  return {
    projects: ps.length, budget: ps.reduce((s, p) => s + p.budget, 0),
    original: ps.reduce((s, p) => s + ((p.extra.originalBudget as number | null) ?? 0), 0),
    originalPeriod: periods.length ? Math.max(...periods) : null,
  }
}

/** One row of mta_mega_statements.json: what MTA said of a mega project in a dated document (pipeline/mta_growth.py). */
export interface Statement {
  mega_project: string; document: string; url: string; statement_date: string; setting: string
  kind: string; value: string; quote: string; note: string | null
}

/** A mega project's statements by kind, the latest of each kind winning. */
export function statementsFor(name: string, rows: Statement[]): Map<string, Statement> {
  const out = new Map<string, Statement>()
  for (const r of rows.filter((r) => r.mega_project === name).sort((a, b) => a.statement_date.localeCompare(b.statement_date))) out.set(r.kind, r)
  return out
}

/** '2030-Q2' -> 'the second quarter of 2030'; anything else as given. */
export function quarterLabel(v: string): string {
  const m = /^(\d{4})-Q([1-4])$/.exec(v)
  return m ? `the ${['first', 'second', 'third', 'fourth'][Number(m[2]) - 1]} quarter of ${m[1]}` : v
}

export interface SiteDot { id: string; program: string; tier: string; lon: number; lat: number; budget: number }

/** One dot per site of every unfinished project placed at a point (Tiers A and B): a multi-site project (35 stations
 * of a signal job, ten bridges) at each of its sites with its share of the money, as on the map tool. */
export function siteDots(projects: Project[], sites: Map<string, Site[]>): SiteDot[] {
  return projects.filter((p) => p.status === 'current' && p.onMap && p.lon !== null && p.lat !== null && (p.tier === 'A' || p.tier === 'B'))
    .flatMap((p) => {
      const ss = sites.get(p.id)
      const at = ss && ss.length > 1 ? ss : [{ lon: p.lon!, lat: p.lat!, share: 1 }]
      return at.map((s) => ({ id: p.id, program: p.program, tier: p.tier, lon: s.lon, lat: s.lat, budget: p.budget * s.share }))
    })
}

export interface SiteGroup { lon: number; lat: number; projects: number; budget: number; byProgram: Record<string, number>; lead: string }

/** Dots at the same point (to 5 decimals, about a metre) as one: the projects there, their money in all and by
 * program, and the program with most of it. A school building's many SCA projects, or city and SCA work at one school,
 * become one dot. */
export function siteGroups(dots: SiteDot[]): SiteGroup[] {
  const g = new Map<string, SiteGroup & { ids: Set<string> }>()
  for (const d of dots) {
    const k = `${d.lon.toFixed(5)},${d.lat.toFixed(5)}`
    const cur = g.get(k) ?? { lon: d.lon, lat: d.lat, projects: 0, budget: 0, byProgram: {}, lead: d.program, ids: new Set<string>() }
    cur.ids.add(d.id)
    cur.budget += d.budget
    cur.byProgram[d.program] = (cur.byProgram[d.program] ?? 0) + d.budget
    g.set(k, cur)
  }
  return [...g.values()].map(({ ids, ...x }) => ({
    ...x, projects: ids.size, lead: Object.entries(x.byProgram).sort((a, b) => b[1] - a[1])[0][0],
  }))
}

export const money = (x: number) => (Math.abs(x) >= 1e9 ? `$${(x / 1e9).toFixed(1)}B` : `$${Math.round(x / 1e6).toLocaleString()}M`)
export const perResident = (x: number) => `$${Math.round(x).toLocaleString()}`

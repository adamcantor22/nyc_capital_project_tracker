const BORO: Record<string, string> = { '1': 'Manhattan', '2': 'Bronx', '3': 'Brooklyn', '4': 'Queens', '5': 'Staten Island' }

/** 401 -> "Queens 1" (DCP borough code + district number). */
export function districtName(code: string): string {
  return `${BORO[code[0]] ?? code[0]} ${Number(code.slice(1))}`
}

export const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

/** 202605 -> "May 2026" */
export const periodLabel = (p: number) => `${MONTHS[(p % 100) - 1]} ${Math.floor(p / 100)}`

export const periodDate = (p: number) => new Date(Math.floor(p / 100), (p % 100) - 1, 1)

/** "Dec 2025" */
export const fmtDate = (d: Date) => `${MONTHS[d.getMonth()]} ${d.getFullYear()}`

/** "2025-12-01" or "2025-12-01 00:00:00" -> that calendar day in local time (new Date() would read the
 * date-only form as UTC midnight, which is the previous evening in New York). */
export function parseDay(s: string): Date {
  const [y, m, d] = s.slice(0, 10).split('-').map(Number)
  return new Date(y, m - 1, d)
}

/** Whole months from a to b, as "2 yr 3 mo" / "5 mo". */
export function spanLabel(a: Date, b: Date): string {
  const m = Math.max(0, (b.getFullYear() - a.getFullYear()) * 12 + b.getMonth() - a.getMonth())
  const y = Math.floor(m / 12)
  const r = m % 12
  return y ? (r ? `${y} yr ${r} mo` : `${y} yr`) : `${r} mo`
}

interface WhenInput {
  phase: string | null
  phaseGroup: string
  startDate: string | null
  forecastCompletion: string | null
  milestones: { designStart: string | null; designEnd: string | null; constructionStart: string | null; constructionEnd: string | null; phaseStart: string | null }
}

/** Where the project is, then the dates that matter for that phase, in one line:
 * "Construction finished Jun 2022; in close-out since" / "In construction since Mar 2025, due May 2031 (in 4 yr 7 mo)".
 * The phase wins over milestone dates that contradict it (a construction end reported while the phase is
 * still construction is ignored). */
export function whenLabel(p: WhenInput, now: Date): string | null {
  const m = p.milestones
  const d = (s: string | null) => (s ? parseDay(s) : null)
  const f = d(p.forecastCompletion)
  const ph = (p.phase ?? '').toLowerCase().replace(/[()]/g, '').trim()
  const due = f ? (f < now ? `forecast finish ${fmtDate(f)} has passed` : `due ${fmtDate(f)} (in ${spanLabel(now, f)})`) : null
  const since = (s: string | null) => (d(s) ? ` since ${fmtDate(d(s)!)}` : '')
  const join = (...xs: (string | null)[]) => {
    const t = xs.filter(Boolean).join(', ')
    return t ? t[0].toUpperCase() + t.slice(1) : null
  }
  if (p.phaseGroup === 'Done' || ph === 'completed') {
    const end = d(m.constructionEnd) ?? f
    return end ? `Finished ${fmtDate(end)}` : 'Finished'
  }
  if (ph === 'close-out' || ph === 'closeout') {
    const end = d(m.constructionEnd) ?? (f && f < now ? f : null)
    return end ? `Construction finished ${fmtDate(end)}; in close-out (final inspections and payments)` : 'In close-out (final inspections and payments)'
  }
  if (ph === 'construction') return join(`in construction${since(m.constructionStart ?? m.phaseStart)}`, due)
  if (ph === 'construction procurement') return join(`hiring a contractor${since(m.phaseStart)}`, due)
  if (ph === 'design' || ph === 'pre-design') return join(`${ph === 'design' ? 'in design' : 'in planning'}${since(m.designStart ?? m.phaseStart)}`, f ? `finish forecast ${fmtDate(f)}` : null)
  if (p.phaseGroup === 'Not started') return join('not started', f ? `finish forecast ${fmtDate(f)}` : null)
  const s = d(p.startDate)
  return join(s ? `started ${fmtDate(s)}` : null, due)
}

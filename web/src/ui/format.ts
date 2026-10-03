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

/** The project's dates in one line: "Started Mar 2022 · due Jun 2027, in 1 yr 8 mo". */
export function whenLabel(start: string | null, finish: string | null, done: boolean, now: Date): string | null {
  const s = start ? parseDay(start) : null
  const f = finish ? parseDay(finish) : null
  const end = !f ? null : done ? `finished ${fmtDate(f)}` : f < now ? `due ${fmtDate(f)} (date has passed)` : `due ${fmtDate(f)}, in ${spanLabel(now, f)}`
  const parts = [s ? `started ${fmtDate(s)}` : null, end].filter(Boolean).join(' · ')
  return parts ? parts[0].toUpperCase() + parts.slice(1) : null
}

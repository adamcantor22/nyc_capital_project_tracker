import { fmtDate, parseDay, periodLabel } from '../ui/format'
import type { ScheduleSnap } from './data'

/** In plain words: how the forecast finish moved between the first and latest report. */
export function slipSummary(rows: ScheduleSnap[]): string {
  const first = rows[0]
  const last = rows.at(-1)!
  const f = parseDay(first.completion_date!)
  const l = parseDay(last.completion_date!)
  if (last.completion_type === 'Actual') {
    const late = monthsBetween(f, l)
    return `Completed ${fmtDate(l)}${rows.length > 1 && late ? `, ${Math.abs(late)} month${Math.abs(late) === 1 ? '' : 's'} ${late > 0 ? 'later' : 'earlier'} than first forecast` : ''}.`
  }
  if (rows.length === 1) return `Forecast to finish ${fmtDate(l)}.`
  const m = monthsBetween(f, l)
  if (m === 0) return `Forecast to finish ${fmtDate(l)}, unchanged since ${periodLabel(first.period)}.`
  return `Forecast to finish ${fmtDate(l)}: ${Math.abs(m)} month${Math.abs(m) === 1 ? '' : 's'} ${m > 0 ? 'later' : 'earlier'} than forecast in ${periodLabel(first.period)}.`
}

function monthsBetween(a: Date, b: Date) {
  return (b.getFullYear() - a.getFullYear()) * 12 + b.getMonth() - a.getMonth()
}

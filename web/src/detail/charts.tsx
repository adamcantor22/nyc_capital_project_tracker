import { useState } from 'react'
import { money } from '../measures/registry'
import type { FundingRow, HistoryRow, ScheduleSnap } from './data'

import { fmtDate, parseDay, periodDate, periodLabel } from '../ui/format'
import { slipSummary } from './schedule'

const TODAY = Date.now()

/** Budget (ink step line) and spend to date (tinted area) across reports. */
export function BudgetHistory({ rows, tint }: { rows: HistoryRow[]; tint: string }) {
  const [hover, setHover] = useState<number | null>(null)
  if (rows.length < 2) return <p className="muted">Reported once, so there is no history yet.</p>
  const W = 320, H = 120, L = 4, R = 4, T = 10, B = 18
  const max = Math.max(...rows.map((r) => Math.max(r.budget, r.spend ?? 0))) || 1
  const x = (i: number) => L + (i * (W - L - R)) / (rows.length - 1)
  const y = (v: number) => T + (1 - v / max) * (H - T - B)
  const step = (vals: number[]) => `M${x(0)},${y(vals[0])}` + vals.slice(1).map((v, i) => `H${x(i + 1)}V${y(v)}`).join('')
  const budget = rows.map((r) => r.budget)
  const spend = rows.map((r) => r.spend ?? 0)
  const h = hover ?? rows.length - 1
  return (
    <figure className="chart">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Budget from ${money(budget[0])} to ${money(budget.at(-1)!)} across ${rows.length} reports`}>
        <line x1={L} x2={W - R} y1={y(0)} y2={y(0)} className="axis" />
        <path d={`${step(spend)}V${y(0)}H${x(0)}Z`} fill={tint} opacity="0.35" />
        <path d={step(budget)} className="line" />
        <line x1={x(h)} x2={x(h)} y1={T} y2={y(0)} className="cross" />
        <circle cx={x(h)} cy={y(budget[h])} r="3.5" className="dot" />
        {rows.map((r, i) => (
          <rect key={r.period} x={x(i) - (W - L - R) / (rows.length - 1) / 2} y={0} width={(W - L - R) / (rows.length - 1)} height={H} fill="transparent"
            onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)} />
        ))}
        <text x={L} y={H - 4} className="tick">{periodLabel(rows[0].period)}</text>
        <text x={W - R} y={H - 4} className="tick" textAnchor="end">{periodLabel(rows.at(-1)!.period)}</text>
      </svg>
      <figcaption>
        <strong>{periodLabel(rows[h].period)}</strong>: budget {money(rows[h].budget)}, spent {money(rows[h].spend)}
        {rows[h].phase ? ` · ${rows[h].phase}` : ''}
        <span className="key-inline"><i className="k-line" /> budget <i className="k-area" style={{ background: tint }} /> spent</span>
      </figcaption>
    </figure>
  )
}

/** One bar per report, from the report date to the finish it forecast. Bar length is the exact time
 * still to go, so a schedule that slips shows bars that stop shrinking or grow. */
export function ScheduleSlip({ snaps, tint }: { snaps: ScheduleSnap[]; tint: string }) {
  const rows = snaps.filter((s) => s.completion_date && !s.variance_implausible)
  if (!rows.length) return <p className="muted">No completion date reported.</p>
  const now = TODAY
  const start = periodDate(rows[0].period).getTime()
  const ends = rows.map((s) => parseDay(s.completion_date!).getTime())
  const end = Math.max(...ends, now)
  const W = 320, rowH = 15, T = 4, axisH = 16, labelW = 54, endW = 50
  const H = T + rows.length * rowH + axisH
  const x = (t: number) => labelW + ((t - start) / (end - start || 1)) * (W - labelW - endW)
  const years: number[] = []
  for (let yr = new Date(start).getFullYear() + 1; yr <= new Date(end).getFullYear(); yr++) years.push(yr)
  const every = Math.ceil(years.length / 5)
  const hasActual = rows.some((s) => s.completion_type === 'Actual')
  return (
    <figure className="chart">
      <p className="sched-headline">{slipSummary(rows)}</p>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={slipSummary(rows)}>
        {years.filter((_, i) => i % every === 0).map((yr) => {
          const t = new Date(yr, 0, 1).getTime()
          return (
            <g key={yr}>
              <line x1={x(t)} x2={x(t)} y1={T} y2={H - axisH + 2} className="grid" />
              <text x={x(t)} y={H - 4} className="tick" textAnchor="middle">{yr}</text>
            </g>
          )
        })}
        <line x1={x(now)} x2={x(now)} y1={T - 2} y2={H - axisH + 2} className="today" />
        <text x={x(now)} y={T + rows.length * rowH + 9} className="tick today-label" textAnchor="middle">today</text>
        {rows.map((s, i) => {
          const y0 = T + i * rowH
          const a = x(periodDate(s.period).getTime())
          const b = x(parseDay(s.completion_date!).getTime())
          const actual = s.completion_type === 'Actual'
          const labelled = i === 0 || i === rows.length - 1
          return (
            <g key={s.period}>
              <title>{`${periodLabel(s.period)} report: ${actual ? 'completed' : 'forecast to finish'} ${fmtDate(parseDay(s.completion_date!))}${s.variance_days ? ` (${s.variance_days > 0 ? '+' : ''}${s.variance_days} days vs the previous report)` : ''}`}</title>
              <text x={labelW - 6} y={y0 + rowH - 4} className="tick" textAnchor="end">{periodLabel(s.period)}</text>
              <rect x={Math.min(a, b)} y={y0 + 4} width={Math.max(1, Math.abs(b - a))} height={rowH - 8} rx="1.5"
                fill={actual ? 'var(--ink)' : tint} opacity={actual ? 1 : 0.55} />
              <circle cx={b} cy={y0 + rowH / 2} r="3.2" fill={actual ? 'var(--ink)' : tint} stroke="var(--ink)" strokeWidth="1" />
              {labelled && <text x={b + 6} y={y0 + rowH - 4} className="tick end-label">{fmtDate(parseDay(s.completion_date!))}</text>}
            </g>
          )
        })}
      </svg>
      <figcaption className="sched-key">
        <span>Each row is one report: the bar runs from that report to the finish date it forecast.</span>
        <span className="key-inline">
          <i className="k-bar" style={{ background: tint }} /> forecast
          {hasActual && <><i className="k-bar" style={{ background: 'var(--ink)' }} /> completed</>}
        </span>
      </figcaption>
    </figure>
  )
}

/** City vs non-city money: one split bar, with a table by fiscal year behind a disclosure. */
export function FundingSplit({ rows, tint }: { rows: FundingRow[]; tint: string }) {
  const city = rows.reduce((s, r) => s + r.city, 0)
  const non = rows.reduce((s, r) => s + r.non_city, 0)
  const total = city + non
  if (!total) return <p className="muted">No funding by fiscal year reported.</p>
  return (
    <div className="funding">
      <div className="split" role="img" aria-label={`City ${money(city)}, non-city ${money(non)}`}>
        <span style={{ flexGrow: city / total }} className="s-city" />
        {non > 0 && <span style={{ flexGrow: non / total, background: tint }} />}
      </div>
      <p className="split-labels">
        <span><i className="k-city" /> City {money(city)} ({Math.round((100 * city) / total)}%)</span>
        <span><i style={{ background: tint }} /> Non-city {money(non)}</span>
      </p>
      <details>
        <summary>By fiscal year</summary>
        <table className="fy">
          <thead><tr><th scope="col">Fiscal year</th><th scope="col">City</th><th scope="col">Non-city</th></tr></thead>
          <tbody>
            {rows.filter((r) => r.city || r.non_city).map((r) => (
              <tr key={r.fy}><th scope="row">FY{r.fy}</th><td>{money(r.city)}</td><td>{money(r.non_city)}</td></tr>
            ))}
          </tbody>
        </table>
      </details>
    </div>
  )
}

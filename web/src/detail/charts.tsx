import { money } from '../measures/registry'
import { fmtDate, parseDay, periodDate, periodLabel } from '../ui/format'
import { moneyTicks, useScrub } from './chartkit'
import type { FundingRow, HistoryRow, ScheduleSnap } from './data'
import { slipSummary } from './schedule'

const TODAY = Date.now()
const PAD = { L: 40, R: 6, T: 8, B: 18 }

/** Budget (ink step line) and spend to date (tinted area) across reports; drag to read any report. */
export function BudgetHistory({ rows, tint }: { rows: HistoryRow[]; tint: string }) {
  const W = 320, H = 130
  const n = rows.length
  const x = (i: number) => PAD.L + (i * (W - PAD.L - PAD.R)) / Math.max(1, n - 1)
  const { index, handlers } = useScrub(n, x, W)
  if (n < 2) return <p className="muted">Reported once, so there is no history yet.</p>
  const ticks = moneyTicks(Math.max(...rows.map((r) => Math.max(r.budget, r.spend ?? 0))))
  const top = ticks.at(-1)!.v || 1
  const y = (v: number) => PAD.T + (1 - v / top) * (H - PAD.T - PAD.B)
  const step = (vals: number[]) => `M${x(0)},${y(vals[0])}` + vals.slice(1).map((v, i) => `H${x(i + 1)}V${y(v)}`).join('')
  const budget = rows.map((r) => r.budget)
  const spend = rows.map((r) => r.spend ?? 0)
  const h = index ?? n - 1
  return (
    <figure className="chart">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Budget from ${money(budget[0])} to ${money(budget.at(-1)!)} across ${n} reports. Use arrow keys to step through reports.`} {...handlers}>
        {ticks.map((t) => (
          <g key={t.v}>
            <line x1={PAD.L} x2={W - PAD.R} y1={y(t.v)} y2={y(t.v)} className={t.v ? 'grid' : 'axis'} />
            <text x={PAD.L - 5} y={y(t.v) + 3} className="tick" textAnchor="end">{t.label}</text>
          </g>
        ))}
        <path d={`${step(spend)}V${y(0)}H${x(0)}Z`} fill={tint} opacity="0.35" />
        <path d={step(budget)} className="line" />
        <line x1={x(h)} x2={x(h)} y1={PAD.T} y2={y(0)} className="cross" />
        <circle cx={x(h)} cy={y(budget[h])} r="4" className="dot" />
        <text x={PAD.L} y={H - 4} className="tick">{periodLabel(rows[0].period)}</text>
        <text x={W - PAD.R} y={H - 4} className="tick" textAnchor="end">{periodLabel(rows.at(-1)!.period)}</text>
      </svg>
      <figcaption>
        <strong>{periodLabel(rows[h].period)}</strong>: budget {money(rows[h].budget)}, spent {money(rows[h].spend)}
        {rows[h].phase ? ` · ${rows[h].phase}` : ''}
        <span className="key-inline"><i className="k-line" /> budget <i className="k-area" style={{ background: tint }} /> spent</span>
      </figcaption>
      <p className="hint">Drag across the chart to read each report.</p>
    </figure>
  )
}

/** Milestone trend: x is when each report came out, y is the finish date it forecast, as one stepped
 * line. Flat means on track, rising means slipping. The diagonal is where report date equals finish
 * date: a project finishes when its line meets it. */
export function ScheduleSlip({ snaps, tint }: { snaps: ScheduleSnap[]; tint: string }) {
  const rows = snaps.filter((s) => s.completion_date && !s.variance_implausible)
  const W = 320, H = 170, L = 46, R = 8, T = 8, B = 18
  const rx = rows.map((s) => periodDate(s.period).getTime())
  const ry = rows.map((s) => parseDay(s.completion_date!).getTime())
  const x0 = rx[0], x1 = Math.max(rx.at(-1) ?? 0, TODAY)
  const y0 = Math.min(...ry, x0), y1 = Math.max(...ry, x1)
  const pad = (y1 - y0) * 0.06 || 864e5 * 30
  const x = (t: number) => L + ((t - x0) / (x1 - x0 || 1)) * (W - L - R)
  const y = (t: number) => T + (1 - (t - (y0 - pad)) / (y1 + pad - (y0 - pad))) * (H - T - B)
  const { index, handlers } = useScrub(rows.length, (i) => x(rx[i]), W)
  if (!rows.length) return <p className="muted">No completion date reported.</p>
  const h = index ?? rows.length - 1
  const path = `M${x(rx[0])},${y(ry[0])}` + rows.slice(1).map((_, i) => `H${x(rx[i + 1])}V${y(ry[i + 1])}`).join('') +
    (rows.at(-1)!.completion_type === 'Actual' ? '' : `H${x(x1)}`)
  const yrs = (a: number, b: number) => {
    const out: number[] = []
    for (let yr = new Date(a).getFullYear() + 1; yr <= new Date(b).getFullYear(); yr++) out.push(yr)
    const every = Math.ceil(out.length / 4)
    return out.filter((_, i) => i % every === 0)
  }
  const s = rows[h]
  const diag = [Math.max(x0, y0 - pad), Math.min(x1, y1 + pad)]
  return (
    <figure className="chart">
      <p className="sched-headline">{slipSummary(rows)}</p>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${slipSummary(rows)} Use arrow keys to step through reports.`} {...handlers}>
        {yrs(y0 - pad, y1 + pad).map((yr) => {
          const t = new Date(yr, 0, 1).getTime()
          return (
            <g key={`y${yr}`}>
              <line x1={L} x2={W - R} y1={y(t)} y2={y(t)} className="grid" />
              <text x={L - 5} y={y(t) + 3} className="tick" textAnchor="end">{yr}</text>
            </g>
          )
        })}
        {yrs(x0, x1).map((yr) => (
          <text key={`x${yr}`} x={x(new Date(yr, 0, 1).getTime())} y={H - 4} className="tick" textAnchor="middle">{yr}</text>
        ))}
        {diag[1] > diag[0] && <line x1={x(diag[0])} y1={y(diag[0])} x2={x(diag[1])} y2={y(diag[1])} className="finish-line" />}
        <line x1={x(TODAY)} x2={x(TODAY)} y1={T} y2={H - B} className="today" />
        <path d={path} fill="none" stroke={tint} strokeWidth="2.5" strokeLinejoin="round" />
        {rows.map((r, i) => (
          <circle key={r.period} cx={x(rx[i])} cy={y(ry[i])} r={i === h ? 4.5 : 2.5}
            fill={r.completion_type === 'Actual' ? 'var(--ink)' : i === h ? tint : '#fff'} stroke="var(--ink)" strokeWidth="1" />
        ))}
      </svg>
      <figcaption>
        <span>
          <strong>{periodLabel(s.period)} report</strong>: {s.completion_type === 'Actual' ? 'completed' : 'forecast to finish'} {fmtDate(parseDay(s.completion_date!))}
          {s.variance_days ? ` (${s.variance_days > 0 ? '+' : '−'}${Math.abs(s.variance_days)} days)` : ''}
        </span>
      </figcaption>
      <p className="hint">Each step is a report. Higher means a later finish; the dashed diagonal is where the finish date arrives.</p>
    </figure>
  )
}

/** City vs non-city money, and how the current budget is spread over fiscal years. */
export function Funding({ rows, tint, budget }: { rows: FundingRow[]; tint: string; budget: number }) {
  const years = rows.filter((r) => r.city || r.non_city)
  const city = rows.reduce((s, r) => s + r.city, 0)
  const non = rows.reduce((s, r) => s + r.non_city, 0)
  const total = city + non
  const W = 320, H = 110, L = 40, R = 6, T = 8, B = 18
  const bw = years.length ? (W - L - R) / years.length : 0
  const { index, handlers } = useScrub(years.length, (i) => L + bw * (i + 0.5), W)
  if (!total) return <p className="muted">No funding by fiscal year reported.</p>
  const ticks = moneyTicks(Math.max(...years.map((r) => r.city + r.non_city)))
  const top = ticks.at(-1)!.v || 1
  const y = (v: number) => T + (1 - v / top) * (H - T - B)
  const h = index ?? null
  const gap = bw > 6 ? 2 : 1
  return (
    <div className="funding">
      {non > 0 ? (
        <>
          <div className="split" role="img" aria-label={`City ${money(city)}, non-city ${money(non)}`}>
            <span style={{ flexGrow: city / total }} className="s-city" />
            <span style={{ flexGrow: non / total, background: tint }} />
          </div>
          <p className="split-labels">
            <span><i className="k-city" /> City {money(city)} ({Math.round((100 * city) / total)}%)</span>
            <span><i style={{ background: tint }} /> Non-city (state, federal, private) {money(non)}</span>
          </p>
        </>
      ) : (
        <p>All city funds.</p>
      )}
      {years.length > 1 && (
        <figure className="chart fy-chart">
          <figcaption className="fy-title">The current budget{Math.abs(total - budget) > 1 ? ` (${money(total)} of it)` : ''}, by the fiscal year it is committed in</figcaption>
          <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Budget by fiscal year" {...handlers}>
            {ticks.map((t) => (
              <g key={t.v}>
                <line x1={L} x2={W - R} y1={y(t.v)} y2={y(t.v)} className={t.v ? 'grid' : 'axis'} />
                <text x={L - 5} y={y(t.v) + 3} className="tick" textAnchor="end">{t.label}</text>
              </g>
            ))}
            {years.map((r, i) => {
              const bx = L + i * bw + gap / 2
              return (
                <g key={r.fy} opacity={h === null || h === i ? 1 : 0.45}>
                  <rect x={bx} width={Math.max(1, bw - gap)} y={y(r.city)} height={y(0) - y(r.city)} fill="var(--ink)" />
                  {r.non_city > 0 && <rect x={bx} width={Math.max(1, bw - gap)} y={y(r.city + r.non_city)} height={y(r.city) - y(r.city + r.non_city) - (r.city ? 1 : 0)} fill={tint} />}
                </g>
              )
            })}
            <text x={L} y={H - 4} className="tick">FY{years[0].fy}</text>
            <text x={W - R} y={H - 4} className="tick" textAnchor="end">FY{years.at(-1)!.fy}</text>
          </svg>
          <p className="fy-read">
            {h === null ? 'Drag across the bars to read a year.' : <><strong>FY{years[h].fy}</strong> (July {years[h].fy - 1} to June {years[h].fy}): {money(years[h].city + years[h].non_city)}{years[h].non_city ? `, ${money(years[h].non_city)} non-city` : ''}</>}
          </p>
        </figure>
      )}
      <details>
        <summary>Fiscal years as a table</summary>
        <table className="fy">
          <thead><tr><th scope="col">Fiscal year</th><th scope="col">City</th><th scope="col">Non-city</th></tr></thead>
          <tbody>
            {years.map((r) => (
              <tr key={r.fy}><th scope="row">FY{r.fy}</th><td>{money(r.city)}</td><td>{money(r.non_city)}</td></tr>
            ))}
          </tbody>
        </table>
      </details>
    </div>
  )
}

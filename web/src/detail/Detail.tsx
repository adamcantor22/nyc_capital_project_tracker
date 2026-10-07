import { useEffect, useState } from 'react'
import type { Site } from '../areas/aggregate'
import type { Manifest, Project } from '../data/types'
import { money } from '../measures/registry'
import { themeColor, TIER_LABEL, TIER_NOTE } from '../map/themes'
import { districtName, fmtDate, parseDay, periodLabel, whenLabel } from '../ui/format'
import { BudgetHistory, Funding, ScheduleSlip } from './charts'
import { FLAG_TEXT, loadDetails, loadScaPhases, SOURCE_LABEL, type Details, type ScaPhase } from './data'

interface Props {
  project: Project
  manifest: Manifest
  onClose(): void
  /** Show totals for every project with this value (a link in the panel: "all DDC projects"). */
  onFilter(id: string, value: string): void
  /** Budget totals across current projects, for "what slice is this?" */
  totals: { all: number; n: number; theme: Map<string, number>; agency: Map<string, number> }
  /** This project's sites, when known: several means it is drawn at each, with a share of the budget. */
  sites?: Site[]
}

/** A value that links to every project sharing it ("all DDC projects"). */
function F({ id, v, on, children }: { id: string; v: string; on(id: string, v: string): void; children?: React.ReactNode }) {
  return <button type="button" className="flink" onClick={() => on(id, v)} title={`Totals for every project: ${v}`}>{children ?? v}</button>
}

const NOW = new Date()

/** "0.4%", "12%", "0.03%" */
const share = (part: number, whole: number) => {
  const pc = whole ? (100 * part) / whole : 0
  return `${pc >= 10 ? Math.round(pc) : pc >= 1 ? pc.toFixed(1) : pc >= 0.1 ? pc.toFixed(2) : '<0.1'}%`
}

export default function Detail({ project: p, manifest, onClose, onFilter, totals, sites }: Props) {
  const [d, setD] = useState<Details | null>(null)
  const [phases, setPhases] = useState<Record<string, ScaPhase[]> | null>(null)
  const [err, setErr] = useState(false)
  const sca = p.program === 'sca'
  const mta = p.program === 'mta'
  const city = !sca && !mta
  useEffect(() => {
    if (sca) loadScaPhases(manifest).then(setPhases, () => setErr(true))
    else if (city) loadDetails(manifest).then(setD, () => setErr(true))
  }, [manifest, sca, city])
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    addEventListener('keydown', onKey)
    return () => removeEventListener('keydown', onKey)
  }, [onClose])

  const x = p.extra as { fmsTitle?: string; description?: string; pids?: number[]; source?: string; spreadM?: number; nPoints?: number; communityBoard?: string; category?: string
    building?: string; dsf?: string | null; projectTypes?: string; cityLink?: string | null; locationEvidence?: string; programFigure?: number | null
    acep?: string; capitalPlan?: string }
  const tint = themeColor(p.theme)
  const schedules = d ? (x.pids ?? []).map((pid) => d.schedulesByPid.get(pid)).filter((s) => s && s.snapshots.length) : []
  const where = [
    p.neighborhood ? <span key="n">{p.neighborhood}</span> : null,
    p.district ? <F on={onFilter} key="d" id="district" v={String(p.district)}>{districtName(String(p.district))}</F> : null,
    p.borough ? <F on={onFilter} key="b" id="borough" v={p.borough} /> : null,
  ].filter(Boolean)
  const when = whenLabel(p, NOW)

  return (
    <aside className="detail" aria-labelledby="detail-h">
      <header className="d-head">
        <p className="d-theme"><span className="swatch-sm" style={{ background: tint }} /><F on={onFilter} id="theme" v={p.theme} />{p.subtheme && <> · <F on={onFilter} id="subtheme" v={p.subtheme} /></>}</p>
        <h2 id="detail-h">{p.title}</h2>
        {x.fmsTitle && x.fmsTitle !== p.title && <p className="d-alt">{x.fmsTitle}</p>}
        <button type="button" className="close" onClick={onClose} aria-label="Close project details">
          <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true"><path d="M3 3l10 10M13 3L3 13" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" /></svg>
        </button>
      </header>

      <dl className="facts">
        <div><dt>Phase</dt><dd>{p.phase?.replace(/^\((.*)\)$/, '$1') ?? '—'}{p.phaseGroup !== 'Active' && <span className="muted"> ({p.phaseGroup.toLowerCase()})</span>}</dd></div>
        <div><dt>{sca ? 'Cost (SCA estimate)' : mta ? 'Current budget' : 'Budget'}</dt><dd className="big">{money(p.budget)}</dd></div>
        <div><dt>Spent</dt><dd>{mta ? <span className="muted">Not published</span> : money(p.spend)}{p.spendPct !== null && <span className="muted"> · {p.spendPct}%</span>}</dd></div>
        {city && <div>
          <dt>Since last report</dt>
          <dd className={p.budgetChange ? (p.budgetChange > 0 ? 'up' : 'down') : ''}>{p.budgetChange === null ? 'First report' : p.budgetChange === 0 ? 'No change' : money(p.budgetChange, true)}</dd>
        </div>}
        <div>
          <dt>Managed by</dt>
          <dd>
            {p.agencies.map((a, i) => <span key={a}>{i > 0 && ', '}<F on={onFilter} id="agency" v={a} /></span>)}
            {p.sponsor && p.sponsor !== p.agencies[0] ? <span className="muted"> for <F on={onFilter} id="sponsor" v={p.sponsor} /></span> : null}
          </dd>
        </div>
        {when && <div><dt>When</dt><dd>{when}</dd></div>}
        {where.length > 0 && <div><dt>Where</dt><dd>{where.map((w, i) => <span key={i}>{i > 0 && ' · '}{w}</span>)}</dd></div>}
      </dl>
      {p.status === 'completed' && <p className="banner">Completed. Still listed in the latest report, but out of the default totals.</p>}
      {p.status === 'dropped' && <p className="banner">Not in the latest report. Last reported {periodLabel(p.lastReported)}.</p>}
      {x.description && <p className="desc">{x.description}</p>}

      {mta && <MtaSections p={p} />}
      {sca && <ScaSections p={p} phases={phases?.[p.id]} cityLink={x.cityLink ?? null} programFigure={x.programFigure ?? null} />}
      {err && <p className="banner">{sca ? 'Phases' : 'History and schedules'} could not be loaded.</p>}
      {city && !d && !err && <div className="skeleton light" aria-hidden="true"><span /><span /><span /></div>}
      {d && (
        <>
          <section>
            <h3>Budget across reports</h3>
            <BudgetHistory rows={d.history[p.id] ?? []} tint={tint} />
          </section>
          <section>
            <h3>Where the money comes from</h3>
            <Funding rows={d.funding[p.id] ?? []} budget={p.budget} sources={{ federal: p.budgetFederal, state: p.budgetState, other: p.budgetOther }} />
          </section>
          <section>
            <h3>Schedule</h3>
            {schedules.length === 0 ? (
              <p className="muted">No schedule reported for this project.</p>
            ) : (
              schedules.slice(0, 4).map((s) => {
                const last = s!.snapshots.at(-1)!
                return (
                  <div key={s!.pid} className="sched">
                    {schedules.length > 1 && <p className="sched-name">{s!.name}</p>}
                    <ScheduleSlip snaps={s!.snapshots} tint={tint} latest={manifest.latest_snapshot} />
                    {last.reason && <p className="muted reason">Latest reason for change: {last.reason.toLowerCase()}</p>}
                  </div>
                )
              })
            )}
            {schedules.length > 4 && <p className="muted">{schedules.length - 4} more linked schedules not shown.</p>}
          </section>
        </>
      )}

      {p.status === 'current' && totals.all > 0 && (
        <p className="slice muted">
          This project is {share(p.budget, totals.theme.get(p.theme) ?? 0)} of all {p.theme} money, {share(p.budget, totals.agency.get(p.agencies[0]) ?? 0)} of {p.agencies[0]}'s portfolio and {share(p.budget, totals.all)} of all current capital money.
        </p>
      )}

      <section>
        <h3>How we know where it is</h3>
        <p><span className={`swatch-sm tier tier-${p.tier}`} /> <strong>{TIER_LABEL[p.tier]}.</strong> {TIER_NOTE[p.tier]}</p>
        {x.source && <p className="muted">Source: {SOURCE_LABEL[x.source] ?? x.source}{p.matchedTo ? `, matched to “${p.matchedTo}”` : ''}.</p>}
        {x.locationEvidence && <p className="muted">Record: {x.locationEvidence}.</p>}
        {sites && sites.length > 1 ? (
          <p className="muted">
            {sites.length} sites, each marked on the map with {sites[0].share_method === 'source_proportion' ? 'its share of the budget, in proportion to the Parks tracker’s amounts' : 'an equal share of the budget'} (an estimate).
          </p>
        ) : null}
        {p.outsideNyc && <p className="muted">Outside the five boroughs ({p.outsideNyc === 'near' ? 'near the city' : city ? 'upstate water supply' : 'farther out'}).</p>}
        {p.sourceFlag && <p className="banner">{FLAG_TEXT[p.sourceFlag] ?? p.sourceFlag}</p>}
      </section>

      {mta ? (
        <footer className="ids">
          ACEP {x.acep} · {x.capitalPlan}
          <br />Data: MTA Capital Dashboard (data.ny.gov ehz8-ag3n, wcsa-vkhf), loads {periodLabel(p.firstReported)} to {periodLabel(p.lastReported)}.
        </footer>
      ) : sca ? (
        <footer className="ids">
          Building {x.building}{x.dsf ? ` · ${x.dsf.replace(/,/g, ', ')}` : ''} · {x.projectTypes}
          <br />Data: SCA Capital Project Schedules and Budgets (NYC Open Data 2xh6-psuq), updated {manifest.programs.find((g) => g.id === 'sca')?.updated ?? 'unknown'}.
        </footer>
      ) : (
        <footer className="ids">
          FMS ID {p.id}{x.pids?.length ? ` · PID ${x.pids.join(', ')}` : ''}{x.category ? ` · ${x.category.toLowerCase()}` : ''}
          <br />First reported {periodLabel(p.firstReported)}. Data: NYC Open Data capital projects dashboard.
        </footer>
      )}
    </aside>
  )
}

const STATUS_TEXT: Record<string, string> = { complete: 'done', in_progress: 'under way', not_started: 'not started', unknown: 'status unknown' }

/** An SCA project's phases as SCA publishes them, and any city record funding the same work. */
function ScaSections({ p, phases, cityLink, programFigure }: { p: Project; phases?: ScaPhase[]; cityLink: string | null; programFigure: number | null }) {
  const [kind, fms] = cityLink ? cityLink.split(':') : [null, null]
  return (
    <>
      {kind === 'same_work' && (
        <p className="banner">The city’s capital data funds this work through DCAS as FMS ID {fms}. Totals that include city projects count it there, not here.</p>
      )}
      {kind === 'possible' && (
        <p className="muted">City FMS ID {fms} (DCAS) names this building for similar work; SCA does not label it as DCAS-funded, so both are counted.</p>
      )}
      {programFigure !== null && (
        <p className="muted">SCA also lists a program-wide figure of {money(programFigure)} on this school’s rows; only the school’s own spending is counted.</p>
      )}
      <section>
        <h3>Phases</h3>
        {!phases ? <div className="skeleton light" aria-hidden="true"><span /><span /></div> : (
          <table className="phases">
            <thead><tr><th>Phase</th><th>Status</th><th>Dates</th><th className="num">Cost</th><th className="num">Spent</th></tr></thead>
            <tbody>
              {phases.map((r, i) => (
                <tr key={i}>
                  <td>{r.phase}</td>
                  <td>{STATUS_TEXT[r.status] ?? r.status}</td>
                  <td>{[r.start_date && `from ${fmtDay(r.start_date)}`, r.actual_end ? `ended ${fmtDay(r.actual_end)}` : r.planned_end && `planned end ${fmtDay(r.planned_end)}`].filter(Boolean).join(', ') || '—'}</td>
                  <td className="num">{money(r.counted)}</td>
                  <td className="num">{money(r.spent)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <p className="muted">Cost is SCA’s final estimate of actual costs for each phase. {p.spendPct !== null ? `${p.spendPct}% spent so far.` : ''}</p>
      </section>
    </>
  )
}

const fmtDay = (s: string) => fmtDate(parseDay(s))

/** An MTA ACEP's plan figures: MTA's original budget and completion against the current ones, % complete, and how its
 * money is classed (pipeline/mta_spending.csv). MTA publishes no spending to date in this data. */
function MtaSections({ p }: { p: Project }) {
  const x = p.extra as { originalBudget?: number | null; pctComplete?: number | null; forecastMonth?: string | null; originalCompletion?: string | null; spendingKind?: string | null; callsReserve?: boolean; megaProject?: string | null }
  // MTA lists many ACEPs at $0 before they are funded, so a difference from a $0 original is not growth.
  const diff = x.originalBudget ? p.budget - x.originalBudget : null
  return (
    <section>
      <h3>Against MTA's original plan</h3>
      <dl className="facts">
        <div><dt>Original budget</dt><dd>{money(x.originalBudget ?? null)}{diff ? <span className={diff > 0 ? 'up' : 'down'}> · {money(diff, true)}</span> : null}</dd></div>
        <div><dt>Complete</dt><dd>{x.pctComplete != null ? `${x.pctComplete}%` : '—'}</dd></div>
        <div><dt>Completion</dt><dd>{x.forecastMonth ?? '—'}{x.originalCompletion && x.originalCompletion !== x.forecastMonth ? <span className="muted"> (originally {x.originalCompletion})</span> : null}</dd></div>
        <div><dt>Counted as</dt><dd>{x.spendingKind === 'overhead' ? 'Overhead' : 'Physical work'}{x.callsReserve ? <span className="muted"> · money MTA sets aside (reserve)</span> : null}</dd></div>
        {x.megaProject && <div><dt>Part of</dt><dd>{x.megaProject}</dd></div>}
      </dl>
      <p className="muted">The original is the budget MTA published as original in its latest load; MTA restates it for some projects when a plan is amended.</p>
    </section>
  )
}

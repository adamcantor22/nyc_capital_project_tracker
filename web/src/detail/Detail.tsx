import { useEffect, useState } from 'react'
import type { Manifest, Project } from '../data/types'
import { money } from '../measures/registry'
import { themeColor, TIER_LABEL, TIER_NOTE } from '../map/themes'
import { districtName, periodLabel } from '../ui/format'
import { BudgetHistory, Funding, ScheduleSlip, Timeline } from './charts'
import { FLAG_TEXT, loadDetails, SOURCE_LABEL, type Details } from './data'

interface Props {
  project: Project
  manifest: Manifest
  onClose(): void
  /** Show only projects matching this value (a link in the panel: "all DDC projects"). */
  onFilter(id: string, value: string): void
}

/** A value that links to every project sharing it ("all DDC projects"). */
function F({ id, v, on, children }: { id: string; v: string; on(id: string, v: string): void; children?: React.ReactNode }) {
  return <button type="button" className="flink" onClick={() => on(id, v)} title={`Show all projects: ${v}`}>{children ?? v}</button>
}

export default function Detail({ project: p, manifest, onClose, onFilter }: Props) {
  const [d, setD] = useState<Details | null>(null)
  const [err, setErr] = useState(false)
  useEffect(() => {
    loadDetails(manifest).then(setD, () => setErr(true))
  }, [manifest])
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    addEventListener('keydown', onKey)
    return () => removeEventListener('keydown', onKey)
  }, [onClose])

  const x = p.extra as { fmsTitle?: string; description?: string; pids?: number[]; source?: string; spreadM?: number; nPoints?: number; communityBoard?: string; category?: string }
  const tint = themeColor(p.theme)
  const schedules = d ? (x.pids ?? []).map((pid) => d.schedulesByPid.get(pid)).filter((s) => s && s.snapshots.length) : []
  const where = [
    p.neighborhood ? <span key="n">{p.neighborhood}</span> : null,
    p.district ? <F on={onFilter} key="d" id="district" v={String(p.district)}>{districtName(String(p.district))}</F> : null,
    p.borough ? <F on={onFilter} key="b" id="borough" v={p.borough} /> : null,
  ].filter(Boolean)

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
        <div><dt>Phase</dt><dd>{p.phase ?? '—'} <span className="muted">({p.phaseGroup})</span></dd></div>
        <div><dt>Budget</dt><dd className="big">{money(p.budget)}</dd></div>
        <div><dt>Spent</dt><dd>{money(p.spend)}{p.spendPct !== null && <span className="muted"> · {p.spendPct}%</span>}</dd></div>
        <div>
          <dt>Since last report</dt>
          <dd className={p.budgetChange ? (p.budgetChange > 0 ? 'up' : 'down') : ''}>{p.budgetChange === null ? 'First report' : p.budgetChange === 0 ? 'No change' : money(p.budgetChange, true)}</dd>
        </div>
        <div>
          <dt>Managed by</dt>
          <dd>
            {p.agencies.map((a, i) => <span key={a}>{i > 0 && ', '}<F on={onFilter} id="agency" v={a} /></span>)}
            {p.sponsor && p.sponsor !== p.agencies[0] ? <span className="muted"> for <F on={onFilter} id="sponsor" v={p.sponsor} /></span> : null}
          </dd>
        </div>
        {where.length > 0 && <div><dt>Where</dt><dd>{where.map((w, i) => <span key={i}>{i > 0 && ' · '}{w}</span>)}</dd></div>}
      </dl>
      <Timeline start={p.startDate} finish={p.forecastCompletion} tint={tint} done={p.phaseGroup === 'Done'} />
      {p.status === 'dropped' && <p className="banner">Not in the latest report. Last reported {periodLabel(p.lastReported)}.</p>}
      {x.description && <p className="desc">{x.description}</p>}

      {err && <p className="banner">History and schedules could not be loaded.</p>}
      {!d && !err && <div className="skeleton light" aria-hidden="true"><span /><span /><span /></div>}
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
                    <ScheduleSlip snaps={s!.snapshots} tint={tint} />
                    {last.reason && <p className="muted reason">Latest reason for change: {last.reason.toLowerCase()}</p>}
                  </div>
                )
              })
            )}
            {schedules.length > 4 && <p className="muted">{schedules.length - 4} more linked schedules not shown.</p>}
          </section>
        </>
      )}

      <section>
        <h3>How we know where it is</h3>
        <p><span className={`swatch-sm tier tier-${p.tier}`} /> <strong>{TIER_LABEL[p.tier]}.</strong> {TIER_NOTE[p.tier]}</p>
        {x.source && <p className="muted">Source: {SOURCE_LABEL[x.source] ?? x.source}{p.matchedTo ? `, matched to “${p.matchedTo}”` : ''}.</p>}
        {x.nPoints && x.nPoints > 1 ? <p className="muted">{x.nPoints} sites; the pin is their average.</p> : null}
        {p.outsideNyc && <p className="muted">Outside the five boroughs ({p.outsideNyc === 'near' ? 'near the city' : 'upstate water supply'}).</p>}
        {p.sourceFlag && <p className="banner">{FLAG_TEXT[p.sourceFlag] ?? p.sourceFlag}</p>}
      </section>

      <footer className="ids">
        FMS ID {p.id}{x.pids?.length ? ` · PID ${x.pids.join(', ')}` : ''}{x.category ? ` · ${x.category.toLowerCase()}` : ''}
        <br />First reported {periodLabel(p.firstReported)}. Data: NYC Open Data capital projects dashboard.
      </footer>
    </aside>
  )
}

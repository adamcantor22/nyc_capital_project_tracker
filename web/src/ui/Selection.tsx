import type { Project } from '../data/types'
import { summarize } from '../measures/aggregate'
import { money } from '../measures/registry'
import { themeColor } from '../map/themes'

interface Props {
  projects: Project[]
  onOpen(id: string): void
  onClear(): void
}

/** Totals for the projects inside a drawn box. */
export default function Selection({ projects, onOpen, onClear }: Props) {
  const s = summarize(projects)
  const maxTheme = s.byTheme[0]?.[1] || 1
  const top = [...projects].sort((a, b) => b.budget - a.budget).slice(0, 12)
  return (
    <aside className="detail selection" aria-labelledby="sel-h">
      <header className="d-head">
        <h2 id="sel-h">{s.n.toLocaleString()} project{s.n === 1 ? '' : 's'} in this area</h2>
        <p className="d-alt">Pinned projects only: exact sites{s.approximate ? `, plus ${s.approximate} matched facilities (approximate)` : ''}. Projects known only to a district or borough are not counted.</p>
        <button type="button" className="close" onClick={onClear} aria-label="Clear the selected area">
          <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true"><path d="M3 3l10 10M13 3L3 13" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" /></svg>
        </button>
      </header>
      {s.n === 0 ? (
        <p className="muted">No pinned projects in this box. Draw a larger area or clear a filter.</p>
      ) : (
        <>
          <dl className="facts">
            <div><dt>Budget</dt><dd className="big">{money(s.budget)}</dd></div>
            <div><dt>Spent</dt><dd>{money(s.spend)} <span className="muted">· {s.budget ? Math.round((100 * s.spend) / s.budget) : 0}%</span></dd></div>
            <div><dt>Change since last report</dt><dd className={s.change > 0 ? 'up' : s.change < 0 ? 'down' : ''}>{money(s.change, true)} <span className="muted">· {s.changed} projects</span></dd></div>
            <div><dt>Non-city funds</dt><dd>{money(s.nonCity)}</dd></div>
          </dl>
          <section>
            <h3>By theme</h3>
            <ul className="bars">
              {s.byTheme.map(([t, b]) => (
                <li key={t}>
                  <span className="bar-label">{t}</span>
                  <span className="bar-track"><span style={{ width: `${(100 * b) / maxTheme}%`, background: themeColor(t) }} /></span>
                  <span className="bar-num">{money(b)}</span>
                </li>
              ))}
            </ul>
          </section>
          <section>
            <h3>By phase</h3>
            <p>{s.byPhase.map(([ph, n]) => `${ph} ${n}`).join(' · ')}</p>
          </section>
          <section>
            <h3>Largest projects</h3>
            <ol className="sel-list">
              {top.map((p) => (
                <li key={p.id}>
                  <button type="button" className="link-row" onClick={() => onOpen(p.id)}>
                    <span className="swatch-sm" style={{ background: themeColor(p.theme) }} />
                    <span>{p.title}</span>
                    <span className="muted">{money(p.budget)}</span>
                  </button>
                </li>
              ))}
            </ol>
          </section>
        </>
      )}
    </aside>
  )
}

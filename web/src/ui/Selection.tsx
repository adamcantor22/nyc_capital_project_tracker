import { useState } from 'react'
import type { Project } from '../data/types'
import { summarize } from '../measures/aggregate'
import { money } from '../measures/registry'
import { OTHER_COLOR, THEME_SLOTS, themeColor } from '../map/themes'
import Donut, { type Slice } from './Donut'

interface Props {
  title: string
  note: string
  projects: Project[]
  /** Share of each project counted here (multi-site projects split across areas). */
  weights?: Map<string, number>
  /** Wholes this selection is a slice of: its district, its borough, the city. */
  shares: { label: string; whole: number }[]
  onOpen(id: string): void
  onClear(): void
}

const NAMED = new Set(THEME_SLOTS.map((s) => s.theme))

/** Totals for a drawn box or a tapped area: headline money, its slice of the city, and what it buys. */
export default function Selection({ title, note, projects, weights, shares, onOpen, onClear }: Props) {
  const s = summarize(projects, weights)
  const [hoverTheme, setHoverTheme] = useState<number | null>(null)
  const themeSlices: Slice[] = (() => {
    const m = new Map<string, number>()
    for (const [t, b] of s.byTheme) {
      const k = NAMED.has(t) ? t : 'Other themes'
      m.set(k, (m.get(k) ?? 0) + b)
    }
    return [...THEME_SLOTS.map((x) => x.theme), 'Other themes'].filter((t) => m.get(t))
      .map((t) => ({ label: t, value: m.get(t)!, color: t === 'Other themes' ? OTHER_COLOR : themeColor(t) }))
  })()
  const pct = (w: number) => (w ? Math.min(100, (100 * s.budget) / w) : 0)
  const fmt = (v: number) => (v >= 10 ? Math.round(v) : v >= 1 ? v.toFixed(1) : v >= 0.1 ? v.toFixed(2) : '<0.1')
  const top = [...projects].sort((a, b) => b.budget * (weights?.get(b.id) ?? 1) - a.budget * (weights?.get(a.id) ?? 1)).slice(0, 12)
  return (
    <aside className="detail selection" aria-labelledby="sel-h">
      <header className="d-head">
        <h2 id="sel-h">{title}</h2>
        <p className="d-alt">{s.n.toLocaleString()} project{s.n === 1 ? '' : 's'}. {note}</p>
        <button type="button" className="close" onClick={onClear} aria-label="Close totals">
          <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true"><path d="M3 3l10 10M13 3L3 13" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" /></svg>
        </button>
      </header>
      {s.n === 0 ? (
        <p className="muted">No projects counted here under the current filters.</p>
      ) : (
        <>
          <dl className="facts">
            <div><dt>Budget</dt><dd className="big">{money(s.budget)}</dd></div>
            <div><dt>Spent</dt><dd>{money(s.spend)} <span className="muted">· {s.budget ? Math.round((100 * s.spend) / s.budget) : 0}%</span></dd></div>
            <div><dt>Change since last report</dt><dd className={s.change > 0 ? 'up' : s.change < 0 ? 'down' : ''}>{money(s.change, true)} <span className="muted">· {s.changed} projects</span></dd></div>
            <div><dt>Non-city funds</dt><dd>{money(s.nonCity)}</dd></div>
          </dl>
          <section>
            <h3>What the money is for</h3>
            <div className="donut-row">
              <Donut label="Budget by theme" slices={themeSlices} size={130} thickness={22} hover={hoverTheme} onHover={setHoverTheme} />
              <ul className="donut-key">
                {themeSlices.map((x, i) => (
                  <li key={x.label} className={hoverTheme === null ? '' : hoverTheme === i ? 'on' : 'off'}
                    onPointerEnter={() => setHoverTheme(i)} onPointerLeave={() => setHoverTheme(null)}><span className="swatch-sm" style={{ background: x.color }} /><span>{x.label}</span><span className="muted">{money(x.value)}</span></li>
                ))}
              </ul>
            </div>
          </section>
          <section>
            <h3>By phase</h3>
            <p>{s.byPhase.map(([ph, n]) => `${ph} ${n}`).join(' · ')}</p>
          </section>
          {shares.length > 0 && (
            <section>
              <h3>Share of the money</h3>
              <ul className="shares">
                {shares.map((x) => (
                  <li key={x.label}>
                    <span>of {x.label}</span>
                    <span className="share-bar" aria-hidden="true"><i style={{ width: `${pct(x.whole)}%` }} /></span>
                    <span>{fmt(pct(x.whole))}%</span>
                    <span className="muted">{money(x.whole)}</span>
                  </li>
                ))}
              </ul>
            </section>
          )}
          <section>
            <h3>Largest projects</h3>
            <ol className="sel-list">
              {top.map((p) => (
                <li key={p.id}>
                  <button type="button" className="link-row" onClick={() => onOpen(p.id)}>
                    <span className="swatch-sm" style={{ background: themeColor(p.theme) }} />
                    <span>{p.title}</span>
                    <span className="muted">{money(p.budget * (weights?.get(p.id) ?? 1))}</span>
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

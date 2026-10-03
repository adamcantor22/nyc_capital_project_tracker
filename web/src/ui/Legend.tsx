import { useState } from 'react'
import type { Project } from '../data/types'
import { subKey, type FilterState } from '../filters/registry'
import { money } from '../measures/registry'
import { OTHER_COLOR, THEME_SLOTS, TIER_LABEL, TIER_NOTE } from '../map/themes'
import KeyRow from './KeyRow'

export const OTHER_KEY = '__other'
const AREA_OF: Record<string, 'neighborhoods' | 'districts' | 'boroughs'> = { C: 'neighborhoods', D: 'districts', E: 'boroughs' }
const AREA_WORD: Record<string, string> = { C: 'neighborhood', D: 'district', E: 'borough' }
const NAMED = new Set(THEME_SLOTS.map((s) => s.theme))

interface Props {
  /** Projects under every filter except theme (for the theme rail) */
  themeBase: Project[]
  /** Projects under every filter except tier (for the precision key) */
  tierBase: Project[]
  allThemes: string[]
  /** Every subtheme key of a theme, across all projects */
  subsOf(theme: string): string[]
  filters: FilterState
  onPick(filter: string, values: string[], add: boolean): void
  onPickTheme(themes: string[], add: boolean): void
  onPickSub(theme: string, sub: string, add: boolean): void
  areaLevel: string | null
  onAreaLevel(l: 'neighborhoods' | 'districts' | 'boroughs' | null): void
  onHoverTheme(key: string | null): void
  onHoverTier(tier: string | null): void
}

export default function Legend(props: Props) {
  const { themeBase, tierBase, allThemes, filters } = props
  const [open, setOpen] = useState<Record<string, boolean>>({})
  const selSubs = filters.subtheme ?? []
  const selThemes = filters.theme ?? []
  const selTiers = filters.tier ?? []
  const otherThemes = allThemes.filter((t) => !NAMED.has(t))
  const entries = [
    ...THEME_SLOTS.map((s) => ({ key: s.theme, label: s.theme, color: s.color, themes: [s.theme] })),
    { key: OTHER_KEY, label: `Other: ${otherThemes.join(', ')}`, color: OTHER_COLOR, themes: otherThemes },
  ].map((e) => {
    const ps = themeBase.filter((p) => e.themes.includes(p.theme))
    const whole = e.themes.some((t) => selThemes.includes(t))
    const split = ps.some((p) => selSubs.includes(subKey(p)))
    const subs = ps.some((p) => p.subtheme)
    return { ...e, ps, n: ps.length, b: ps.reduce((s, p) => s + p.budget, 0), on: whole || split, pressed: whole ? true : split ? 'mixed' as const : false, subs }
  })
  const totalB = entries.reduce((s, e) => s + e.b, 0) || 1

  const tiers = ['A', 'B', 'C', 'D', 'E', 'Unplaced'].map((t) => {
    const ps = tierBase.filter((p) => p.tier === t)
    return { t, n: ps.length, b: ps.reduce((s, p) => s + p.budget, 0), on: selTiers.includes(t) }
  })

  return (
    <section className="legend" aria-labelledby="legend-h">
      <h2 id="legend-h">Key</h2>
      <p className="legend-hint">Tap a key to show only those projects. Use ＋ (or hold the key) to add more.</p>

      <h3>What is being built</h3>
      <div className="theme-rail" aria-hidden="true">
        {entries.filter((e) => e.b > 0).map((e) => (
          <span key={e.key} style={{ flexGrow: e.b / totalB, background: e.color }} className={e.on || !selThemes.length ? '' : 'off'} />
        ))}
      </div>
      <ul className="key-list">
        {entries.map((e) => (
          <li key={e.key}>
            <KeyRow
              label={e.key === OTHER_KEY ? 'Other themes' : e.label}
              swatch={<span className="swatch" style={{ background: e.color }} />}
              num={money(e.b)}
              pressed={e.pressed}
              disabled={!e.n && !e.on}
              expanded={e.subs ? (open[e.key] ?? e.pressed === 'mixed') : undefined}
              onExpand={() => setOpen((o) => ({ ...o, [e.key]: !(o[e.key] ?? e.pressed === 'mixed') }))}
              onPick={(add) => props.onPickTheme(e.themes, add)}
              onHover={(on) => props.onHoverTheme(on ? e.key : null)}
            />
            {e.subs && (open[e.key] ?? e.pressed === 'mixed') && (
              <Subthemes
                projects={e.ps}
                color={e.color}
                isOn={(p) => selThemes.includes(p.theme) || selSubs.includes(subKey(p))}
                onPick={(p, add) => props.onPickSub(p.theme, subKey(p), add)}
              />
            )}
          </li>
        ))}
      </ul>
      {otherThemes.length > 0 && <p className="legend-note">Other themes: {otherThemes.join(', ')}.</p>}

      <h3>How precisely we know where</h3>
      <ul className="key-list">
        {tiers.map(({ t, n, b, on }) => AREA_OF[t] ? (
          <li key={t}>
            <button type="button" className="key view-key" aria-pressed={props.areaLevel === AREA_OF[t]}
              onClick={() => props.onAreaLevel(props.areaLevel === AREA_OF[t] ? null : AREA_OF[t])}>
              <span className={`swatch tier tier-${t}`} />
              <span className="key-label">{TIER_LABEL[t]}</span>
              <span className="key-num">{n.toLocaleString()}</span>
            </button>
            <span className="key-sub">{TIER_NOTE[t].replace('shaded, not pinned', 'not pinned')} {money(b)}. Tap for totals by {AREA_WORD[t]}.</span>
          </li>
        ) : (
          <li key={t}>
            <KeyRow
              label={TIER_LABEL[t]}
              swatch={<span className={`swatch tier tier-${t}`} />}
              num={n.toLocaleString()}
              pressed={on}
              disabled={!n && !on}
              title={TIER_NOTE[t]}
              onPick={(add) => props.onPick('tier', [t], add)}
              onHover={(h) => props.onHoverTier(h ? t : null)}
            />
            <span className="key-sub">{TIER_NOTE[t]} {money(b)}.</span>
          </li>
        ))}
      </ul>
    </section>
  )
}

function Subthemes({ projects, color, isOn, onPick }: { projects: Project[]; color: string; isOn(p: Project): boolean; onPick(p: Project, add: boolean): void }) {
  const rows = new Map<string, { p: Project; b: number }>()
  for (const p of projects) {
    const k = subKey(p)
    const r = rows.get(k)
    if (r) r.b += p.budget
    else rows.set(k, { p, b: p.budget })
  }
  const otherLast = (r: { p: Project }) => (r.p.subtheme ? 0 : 1)
  return (
    <ul className="key-list" aria-label="Subthemes">
      {[...rows].sort((a, b) => otherLast(a[1]) - otherLast(b[1]) || b[1].b - a[1].b).map(([k, r]) => (
        <li key={k}>
          <KeyRow
            indent
            label={r.p.subtheme ? k : 'Other'}
            swatch={<span className="swatch sub" style={{ borderColor: color }} />}
            num={money(r.b)}
            pressed={isOn(r.p)}
            onPick={(add) => onPick(r.p, add)}
          />
        </li>
      ))}
    </ul>
  )
}

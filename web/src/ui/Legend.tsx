import type { Project } from '../data/types'
import type { FilterState } from '../filters/registry'
import { money } from '../measures/registry'
import { OTHER_COLOR, THEME_SLOTS, TIER_LABEL, TIER_NOTE } from '../map/themes'
import KeyButton from './KeyButton'

export const OTHER_KEY = '__other'
const NAMED = new Set(THEME_SLOTS.map((s) => s.theme))

interface Props {
  /** Projects under every filter except theme (for the theme rail) */
  themeBase: Project[]
  /** Projects under every filter except tier (for the precision key) */
  tierBase: Project[]
  /** Projects under every filter except subtheme (for subtheme chips) */
  subBase: Project[]
  allThemes: string[]
  filters: FilterState
  onPick(filter: string, values: string[], add: boolean): void
  onHoverTheme(key: string | null): void
  onHoverTier(tier: string | null): void
}

export default function Legend(props: Props) {
  const { themeBase, tierBase, subBase, allThemes, filters } = props
  const selSubs = filters.subtheme ?? []
  const selThemes = filters.theme ?? []
  const selTiers = filters.tier ?? []
  const otherThemes = allThemes.filter((t) => !NAMED.has(t))
  const entries = [
    ...THEME_SLOTS.map((s) => ({ key: s.theme, label: s.theme, color: s.color, themes: [s.theme] })),
    { key: OTHER_KEY, label: `Other: ${otherThemes.join(', ')}`, color: OTHER_COLOR, themes: otherThemes },
  ].map((e) => {
    const ps = themeBase.filter((p) => e.themes.includes(p.theme))
    return { ...e, n: ps.length, b: ps.reduce((s, p) => s + p.budget, 0), on: e.themes.some((t) => selThemes.includes(t)) }
  })
  const totalB = entries.reduce((s, e) => s + e.b, 0) || 1

  const tiers = ['A', 'B', 'C', 'D', 'E', 'Unplaced'].map((t) => {
    const ps = tierBase.filter((p) => p.tier === t)
    return { t, n: ps.length, b: ps.reduce((s, p) => s + p.budget, 0), on: selTiers.includes(t) }
  })

  return (
    <section className="legend" aria-labelledby="legend-h">
      <h2 id="legend-h">Key</h2>
      <p className="legend-hint">Tap a key to show only those projects; hold it (or Shift-click) to add it.</p>

      <h3>What is being built</h3>
      <div className="theme-rail" aria-hidden="true">
        {entries.filter((e) => e.b > 0).map((e) => (
          <span key={e.key} style={{ flexGrow: e.b / totalB, background: e.color }} className={e.on || !selThemes.length ? '' : 'off'} />
        ))}
      </div>
      <ul className="key-list">
        {entries.map((e) => (
          <li key={e.key}>
            <KeyButton
              className="key"
              aria-pressed={e.on}
              disabled={!e.n && !e.on}
              onPick={(add) => props.onPick('theme', e.themes, add)}
              onMouseEnter={() => props.onHoverTheme(e.key)}
              onMouseLeave={() => props.onHoverTheme(null)}
              onFocus={() => props.onHoverTheme(e.key)}
              onBlur={() => props.onHoverTheme(null)}
            >
              <span className="swatch" style={{ background: e.color }} />
              <span className="key-label">{e.key === OTHER_KEY ? 'Other themes' : e.label}</span>
              <span className="key-num">{money(e.b)}</span>
            </KeyButton>
            {e.on && <Subthemes projects={subBase.filter((p) => e.themes.includes(p.theme))} selected={selSubs} onPick={(v, add) => props.onPick('subtheme', v, add)} />}
          </li>
        ))}
      </ul>
      {otherThemes.length > 0 && <p className="legend-note">Other themes: {otherThemes.join(', ')}.</p>}

      <h3>How precisely we know where</h3>
      <ul className="key-list">
        {tiers.map(({ t, n, b, on }) => (
          <li key={t}>
            <KeyButton
              className="key"
              aria-pressed={on}
              disabled={!n && !on}
              title={TIER_NOTE[t]}
              onPick={(add) => props.onPick('tier', [t], add)}
              onMouseEnter={() => props.onHoverTier(t)}
              onMouseLeave={() => props.onHoverTier(null)}
              onFocus={() => props.onHoverTier(t)}
              onBlur={() => props.onHoverTier(null)}
            >
              <span className={`swatch tier tier-${t}`} />
              <span className="key-label">{TIER_LABEL[t]}</span>
              <span className="key-num">{n.toLocaleString()}</span>
            </KeyButton>
            <span className="key-sub">{TIER_NOTE[t]} {money(b)}.</span>
          </li>
        ))}
      </ul>
    </section>
  )
}

function Subthemes({ projects, selected, onPick }: { projects: Project[]; selected: string[]; onPick(v: string[], add: boolean): void }) {
  const counts = new Map<string, number>()
  for (const p of projects) if (p.subtheme) counts.set(p.subtheme, (counts.get(p.subtheme) ?? 0) + 1)
  if (!counts.size) return null
  return (
    <div className="subs" role="group" aria-label="Subthemes">
      {[...counts].sort((a, b) => b[1] - a[1]).map(([sub, n]) => (
        <KeyButton key={sub} className="chip" aria-pressed={selected.includes(sub)} onPick={(add) => onPick([sub], add)}>
          {sub} <span className="key-num">{n}</span>
        </KeyButton>
      ))}
    </div>
  )
}

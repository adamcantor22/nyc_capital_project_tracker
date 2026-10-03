import type { Project } from '../data/types'
import type { FilterState } from '../filters/registry'
import { money } from '../measures/registry'
import { OTHER_COLOR, THEME_SLOTS, TIER_LABEL, TIER_NOTE } from '../map/themes'

export const OTHER_KEY = '__other'
const NAMED = new Set(THEME_SLOTS.map((s) => s.theme))

interface Props {
  /** Projects under every filter except theme (for the theme rail) */
  themeBase: Project[]
  /** Projects under every filter except tier (for the precision key) */
  tierBase: Project[]
  allThemes: string[]
  filters: FilterState
  onToggleTheme(themes: string[]): void
  onToggleTier(tier: string): void
  onHoverTheme(key: string | null): void
  onHoverTier(tier: string | null): void
}

export default function Legend(props: Props) {
  const { themeBase, tierBase, allThemes, filters } = props
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
      <p className="legend-hint">Tap a key to show only those projects.</p>

      <h3>What is being built</h3>
      <div className="theme-rail" aria-hidden="true">
        {entries.filter((e) => e.b > 0).map((e) => (
          <span key={e.key} style={{ flexGrow: e.b / totalB, background: e.color }} className={e.on || !selThemes.length ? '' : 'off'} />
        ))}
      </div>
      <ul className="key-list">
        {entries.map((e) => (
          <li key={e.key}>
            <button
              type="button"
              className="key"
              aria-pressed={e.on}
              disabled={!e.n && !e.on}
              onClick={() => props.onToggleTheme(e.themes)}
              onMouseEnter={() => props.onHoverTheme(e.key)}
              onMouseLeave={() => props.onHoverTheme(null)}
              onFocus={() => props.onHoverTheme(e.key)}
              onBlur={() => props.onHoverTheme(null)}
            >
              <span className="swatch" style={{ background: e.color }} />
              <span className="key-label">{e.key === OTHER_KEY ? 'Other themes' : e.label}</span>
              <span className="key-num">{money(e.b)}</span>
            </button>
          </li>
        ))}
      </ul>
      {otherThemes.length > 0 && <p className="legend-note">Other themes: {otherThemes.join(', ')}.</p>}

      <h3>How precisely we know where</h3>
      <ul className="key-list">
        {tiers.map(({ t, n, b, on }) => (
          <li key={t}>
            <button
              type="button"
              className="key"
              aria-pressed={on}
              disabled={!n && !on}
              title={TIER_NOTE[t]}
              onClick={() => props.onToggleTier(t)}
              onMouseEnter={() => props.onHoverTier(t)}
              onMouseLeave={() => props.onHoverTier(null)}
              onFocus={() => props.onHoverTier(t)}
              onBlur={() => props.onHoverTier(null)}
            >
              <span className={`swatch tier tier-${t}`} />
              <span className="key-label">{TIER_LABEL[t]}</span>
              <span className="key-num">{n.toLocaleString()}</span>
            </button>
            <span className="key-sub">{TIER_NOTE[t]} {money(b)}.</span>
          </li>
        ))}
      </ul>
    </section>
  )
}

import type { FilterState } from '../filters/registry'
import { OTHER_COLOR, THEME_SLOTS } from '../map/themes'
import KeyButton from './KeyButton'

interface Props {
  allThemes: string[]
  filters: FilterState
  subsOf(theme: string): string[]
  onPickTheme(themes: string[], add: boolean): void
}

const NAMED = new Set(THEME_SLOTS.map((s) => s.theme))

/** Phone: the theme key as one sideways row of chips on the map (tap = only this, hold = add). */
export default function ThemeStrip({ allThemes, filters, subsOf, onPickTheme }: Props) {
  const other = allThemes.filter((t) => !NAMED.has(t))
  const items = [
    ...THEME_SLOTS.map((s) => ({ label: s.theme.split(' ')[0].replace(/,$/, ''), full: s.theme, color: s.color, themes: [s.theme] })),
    { label: 'Other', full: `Other themes: ${other.join(', ')}`, color: OTHER_COLOR, themes: other },
  ]
  const th = filters.theme ?? []
  const su = filters.subtheme ?? []
  return (
    <div className="theme-strip" role="group" aria-label="Themes">
      {items.map((it) => {
        const whole = it.themes.some((t) => th.includes(t))
        const split = it.themes.some((t) => subsOf(t).some((s) => su.includes(s)))
        return (
          <KeyButton key={it.label} className="tchip" aria-pressed={whole ? true : split ? 'mixed' : false} title={it.full}
            onPick={(add) => onPickTheme(it.themes, add)}>
            <span className="dot" style={{ background: it.color }} />{it.label}
          </KeyButton>
        )
      })}
    </div>
  )
}

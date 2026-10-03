/** Theme tints. Eight validated categorical hues (dataviz palette, adjacent-pair CVD checked on the
 * sheet colour) in fixed slot order; the four smallest themes share the slate "other" tint. */
export const THEME_SLOTS: { theme: string; color: string }[] = [
  { theme: 'Water and sewer', color: '#2a78d6' },
  { theme: 'Transportation', color: '#eb6834' },
  { theme: 'Economic development and waterfront', color: '#1baf7a' },
  { theme: 'Libraries and culture', color: '#eda100' },
  { theme: 'Health', color: '#e87ba4' },
  { theme: 'Parks', color: '#008300' },
  { theme: 'Government buildings and operations', color: '#4a3aa7' },
  { theme: 'Public safety and justice', color: '#e34948' },
]
export const OTHER_COLOR = '#7b8494'
const byTheme = new Map(THEME_SLOTS.map((s) => [s.theme, s.color]))

export function themeColor(theme: string): string {
  return byTheme.get(theme) ?? OTHER_COLOR
}

export const TIER_LABEL: Record<string, string> = {
  A: 'Exact site',
  B: 'Matched facility',
  C: 'Neighborhood',
  D: 'Community district',
  E: 'Borough',
  Unplaced: 'Citywide or unknown',
}

export const TIER_NOTE: Record<string, string> = {
  A: 'An official point, address or street for this project.',
  B: 'Matched to a named facility or unit; usually within 100 m.',
  C: 'Only the neighborhood is known; shaded, not pinned.',
  D: 'Only the community district is known; shaded, not pinned.',
  E: 'Only the borough is known; shaded, not pinned.',
  Unplaced: 'Citywide programs or no usable location; listed, not mapped.',
}

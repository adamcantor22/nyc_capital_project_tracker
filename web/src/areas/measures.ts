import { money } from '../measures/registry'
import type { AreaMeasure } from './aggregate'

const pct = (v: number) => `${Math.round(v)}%`
const share = (a: number, b: number) => (b > 0 ? (100 * a) / b : null)

/** Adding an area measure (a funding source, a new ratio): one entry here. */
export const areaMeasures: AreaMeasure[] = [
  { id: 'budget', label: 'Total budget', kind: 'seq', value: (a) => a.budget, format: (v) => money(v) },
  { id: 'spent', label: 'Share spent', kind: 'seq', value: (a) => share(a.spend, a.budget), format: pct },
  { id: 'noncity', label: 'Non-city share', kind: 'seq', value: (a) => share(a.nonCity, a.budget), format: pct },
  { id: 'federal', label: 'Federal share (est.)', kind: 'seq', value: (a) => share(a.federal, a.budget), format: pct },
  { id: 'state', label: 'State share (est.)', kind: 'seq', value: (a) => share(a.state, a.budget), format: pct },
  { id: 'change', label: 'Budget change since last report', kind: 'div', value: (a) => a.change, format: (v) => money(v, true) },
]
export const areaMeasureById = Object.fromEntries(areaMeasures.map((m) => [m.id, m]))

const SEQ = ['#e3eefb', '#cde2fb', '#9ec5f4', '#6da7ec', '#3987e5', '#256abf', '#184f95', '#0d366b']
const DIV_NEG = ['#f0efec', '#cde2fb', '#86b6ef', '#3987e5', '#1c5cab']
const DIV_POS = ['#f0efec', '#f8d0cc', '#f09d95', '#e34948', '#a82a26']

function lerp(stops: string[], t: number): string {
  const x = Math.min(1, Math.max(0, t)) * (stops.length - 1)
  const i = Math.min(stops.length - 2, Math.floor(x))
  const f = x - i
  const c = (h: string) => [1, 3, 5].map((k) => parseInt(h.slice(k, k + 2), 16))
  const [a, b] = [c(stops[i]), c(stops[i + 1])]
  return `#${a.map((v, k) => Math.round(v + (b[k] - v) * f).toString(16).padStart(2, '0')).join('')}`
}

/** Colour for a value, given the range of values across areas. Sequential ramps use sqrt scaling so a
 * few huge areas don't wash out the rest; diverging scales are symmetric around zero. */
export function colorFor(kind: 'seq' | 'div', v: number, max: number, min: number): string {
  if (kind === 'seq') return lerp(SEQ, max > 0 ? Math.sqrt(Math.max(0, v) / max) : 0)
  const lim = Math.max(Math.abs(min), Math.abs(max)) || 1
  return v >= 0 ? lerp(DIV_POS, Math.sqrt(v / lim)) : lerp(DIV_NEG, Math.sqrt(-v / lim))
}

export const RAMP = { seq: SEQ, divNeg: DIV_NEG, divPos: DIV_POS }

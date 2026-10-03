import { useState } from 'react'
import { money } from '../measures/registry'

export interface Slice { label: string; value: number; color: string }

interface Props {
  slices: Slice[]
  size?: number
  thickness?: number
  /** Text in the hole; defaults to the hovered slice or the total. */
  center?: React.ReactNode
  sub?: React.ReactNode
  /** Ring on a dark rail rather than the white sheet (sets the gap colour). */
  dark?: boolean
  label: string
}

/** Donut: slices start at 12 o'clock, clockwise, separated by a 2px surface gap. */
export default function Donut({ slices, size = 140, thickness = 22, center, sub, dark, label }: Props) {
  const [hover, setHover] = useState<number | null>(null)
  const total = slices.reduce((s, x) => s + x.value, 0) || 1
  const r = size / 2 - 2
  const ri = r - thickness
  const starts = slices.map((_, i) => slices.slice(0, i).reduce((sum, x) => sum + x.value, 0) / total)
  const arcs = slices.map((s, i) => {
    const a0 = -Math.PI / 2 + starts[i] * Math.PI * 2
    return arc(size / 2, size / 2, r, ri, a0, a0 + (s.value / total) * Math.PI * 2)
  })
  const h = hover !== null ? slices[hover] : null
  return (
    <figure className={`donut${dark ? ' dark' : ''}`} style={{ width: size }}>
      <svg viewBox={`0 0 ${size} ${size}`} width={size} height={size} role="img" aria-label={`${label}: ${slices.map((s) => `${s.label} ${Math.round((100 * s.value) / total)}%`).join(', ')}`}>
        {arcs.map((d, i) => (
          <path key={slices[i].label} d={d} fill={slices[i].color} className="slice" opacity={hover === null || hover === i ? 1 : 0.35}
            onPointerEnter={() => setHover(i)} onPointerLeave={() => setHover(null)} />
        ))}
      </svg>
      <figcaption className="donut-center" style={{ width: ri * 2 }}>
        {h ? (
          <><strong>{Math.round((100 * h.value) / total)}%</strong><span>{h.label}</span><span>{money(h.value)}</span></>
        ) : (
          <>{center ?? <strong>{money(total)}</strong>}{sub && <span>{sub}</span>}</>
        )}
      </figcaption>
    </figure>
  )
}

function arc(cx: number, cy: number, r: number, ri: number, a0: number, a1: number) {
  if (a1 - a0 >= Math.PI * 2 - 1e-6) a1 = a0 + Math.PI * 2 - 1e-4
  const p = (rad: number, a: number) => `${cx + rad * Math.cos(a)},${cy + rad * Math.sin(a)}`
  const large = a1 - a0 > Math.PI ? 1 : 0
  return `M${p(r, a0)}A${r},${r} 0 ${large} 1 ${p(r, a1)}L${p(ri, a1)}A${ri},${ri} 0 ${large} 0 ${p(ri, a0)}Z`
}

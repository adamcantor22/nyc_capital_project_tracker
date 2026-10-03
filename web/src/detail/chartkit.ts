import { useRef, useState } from 'react'
import { money } from '../measures/registry'

/** Drag (or hover) across a chart to scrub through its points. Pointer capture keeps a touch drag on
 * the chart; touch-action: pan-y on the svg leaves vertical scrolling of the panel to the browser. */
export function useScrub(n: number, xOf: (i: number) => number, viewW: number) {
  const [i, setI] = useState<number | null>(null)
  const svg = useRef<SVGSVGElement>(null)
  const nearest = (clientX: number) => {
    const r = svg.current!.getBoundingClientRect()
    const vx = ((clientX - r.left) / r.width) * viewW
    let best = 0
    for (let k = 1; k < n; k++) if (Math.abs(xOf(k) - vx) < Math.abs(xOf(best) - vx)) best = k
    return best
  }
  const handlers = {
    ref: svg,
    onPointerDown: (e: React.PointerEvent<SVGSVGElement>) => {
      e.currentTarget.setPointerCapture(e.pointerId)
      setI(nearest(e.clientX))
    },
    onPointerMove: (e: React.PointerEvent<SVGSVGElement>) => {
      if (e.pointerType === 'mouse' || e.currentTarget.hasPointerCapture(e.pointerId)) setI(nearest(e.clientX))
    },
    onPointerLeave: (e: React.PointerEvent<SVGSVGElement>) => e.pointerType === 'mouse' && setI(null),
    onKeyDown: (e: React.KeyboardEvent<SVGSVGElement>) => {
      if (e.key === 'ArrowLeft') setI((v) => Math.max(0, (v ?? n - 1) - 1))
      if (e.key === 'ArrowRight') setI((v) => Math.min(n - 1, (v ?? n - 1) + 1))
    },
    tabIndex: 0,
    style: { touchAction: 'pan-y' } as React.CSSProperties,
  }
  return { index: i, handlers }
}

/** Three round money ticks from zero to at or above the top of the data (the chart's y domain ends at the last). */
export function moneyTicks(max: number): { v: number; label: string }[] {
  if (max <= 0) return [{ v: 0, label: '$0' }]
  const mag = 10 ** Math.floor(Math.log10(max / 2))
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s * 2 >= max) ?? mag * 10
  return [0, step, step * 2].map((v) => ({ v, label: v === 0 ? '$0' : money(v) }))
}

/** A point under or near a tap, in screen pixels; `direct` when the tap lands on its drawn disc. */
export interface Candidate { id: string; x: number; y: number; direct: boolean }

/** Tap margin around a point's centre, in px: wider for fingers than for a mouse. Provisional values. */
export const TAP_TOLERANCE = { touch: 14, mouse: 6 }

/** The point a tap selects: any point drawn under the tap or centred within `tol` px of it, the nearest centre
 * winning, so a small point beside a large one can still be picked. */
export function pickNearest(cands: Candidate[], at: { x: number; y: number }, tol: number): string | null {
  let best: string | null = null, bestD = Infinity
  for (const c of cands) {
    const d = Math.hypot(c.x - at.x, c.y - at.y)
    if ((c.direct || d <= tol) && d < bestD) { best = c.id; bestD = d }
  }
  return best
}

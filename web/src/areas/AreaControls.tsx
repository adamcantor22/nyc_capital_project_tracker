import type { Level } from './aggregate'
import { areaMeasureById, areaMeasures, RAMP } from './measures'

interface Props {
  level: Level | null
  measure: string
  max: number
  min: number
  onLevel(l: Level | null): void
  onMeasure(id: string): void
  /** Map tools shown under the switch (Select an area). */
  children?: React.ReactNode
}

const LEVELS: [Level | null, string][] = [[null, 'Projects'], ['neighborhoods', 'Neighborhoods'], ['districts', 'Districts'], ['boroughs', 'Boroughs']]

/** Map view switch (projects or totals by area), and in area view the measure picker and its scale. */
export default function AreaControls({ level, measure, max, min, onLevel, onMeasure, children }: Props) {
  const m = areaMeasureById[measure]
  return (
    <div className="area-controls">
      <div className="seg" role="radiogroup" aria-label="Map shows">
        {LEVELS.map(([l, label]) => (
          <button key={label} type="button" role="radio" aria-checked={level === l} className="seg-btn" onClick={() => onLevel(l)}>{label}</button>
        ))}
      </div>
      {children}
      {level && (
        <div className="area-legend">
          <label>
            <span className="visually-hidden">Shade areas by</span>
            <select value={measure} onChange={(e) => onMeasure(e.target.value)}>
              {areaMeasures.map((x) => <option key={x.id} value={x.id}>{x.label}</option>)}
            </select>
          </label>
          <div className="ramp" aria-hidden="true"
            style={{ background: `linear-gradient(90deg, ${m.kind === 'seq' ? RAMP.seq.join(', ') : [...RAMP.divNeg].reverse().concat(RAMP.divPos.slice(1)).join(', ')})` }} />
          <div className="ramp-ends">
            <span>{m.kind === 'div' ? m.format(-Math.max(Math.abs(min), Math.abs(max))) : m.format(0)}</span>
            {m.kind === 'div' && <span>no change</span>}
            <span>{m.kind === 'div' ? m.format(Math.max(Math.abs(min), Math.abs(max))) : m.format(max)}</span>
          </div>
          <p className="area-note">
            {level === 'boroughs' ? 'Counts every project with a borough.' : level === 'districts' ? 'Counts projects located to a district or better; multi-site projects split by site.' : 'Counts projects located to a neighborhood or better; multi-site projects split by site.'}
          </p>
        </div>
      )}
    </div>
  )
}

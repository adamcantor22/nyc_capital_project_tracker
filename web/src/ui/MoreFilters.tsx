import { useState } from 'react'
import type { Project } from '../data/types'
import { filterById, optionCounts, type FilterState } from '../filters/registry'
import { districtName } from './format'

/** Filters not already in the legend key. Order is the order shown. */
const IDS = ['status', 'subtheme', 'phase', 'tier', 'borough', 'district', 'size', 'agency', 'sponsor', 'schedule']

const LABELS: Record<string, Record<string, string>> = {
  status: { current: 'In the latest report', dropped: 'No longer reported' },
  schedule: { yes: 'Has a schedule', no: 'No schedule reported' },
}

interface Props {
  projects: Project[]
  filters: FilterState
  onChange(id: string, values: string[]): void
}

const SHORT = 6

export default function MoreFilters({ projects, filters, onChange }: Props) {
  const [expanded, setExpanded] = useState<Record<string, boolean>>({})
  const activeCount = IDS.filter((id) => id !== 'status' && filters[id]?.length).length
  return (
    <details className="more-filters">
      <summary>
        More filters{activeCount > 0 && <span className="badge">{activeCount}</span>}
      </summary>
      {IDS.map((id) => {
        const def = filterById[id]
        const sel = filters[id] ?? []
        const opts = optionCounts(projects, filters, id)
        for (const v of sel) if (!opts.some(([o]) => o === v)) opts.push([v, 0])
        const long = opts.length > SHORT + 2
        const open = expanded[id] || !long
        // Collapsed long groups still show every selected option.
        const shown = open ? opts : opts.filter(([v], i) => i < SHORT || sel.includes(v))
        return (
          <fieldset key={id} className="fgroup">
            <legend>
              {def.label}
              {sel.length > 0 && (
                <button type="button" className="link" onClick={() => onChange(id, [])}>
                  Clear
                </button>
              )}
            </legend>
            <div className="opts">
              {shown.map(([v, n]) => (
                <label key={v} className="opt">
                  <input
                    type="checkbox"
                    checked={sel.includes(v)}
                    onChange={(e) => onChange(id, e.target.checked ? [...sel, v] : sel.filter((s) => s !== v))}
                  />
                  <span>{LABELS[id]?.[v] ?? (id === 'district' ? districtName(v) : v)}</span>
                  <span className="n">{n.toLocaleString()}</span>
                </label>
              ))}
            </div>
            {long && (
              <button type="button" className="link more-opts" aria-expanded={open} onClick={() => setExpanded((e) => ({ ...e, [id]: !open }))}>
                {open ? 'Show fewer' : `Show all ${opts.length}`}
              </button>
            )}
          </fieldset>
        )
      })}
    </details>
  )
}

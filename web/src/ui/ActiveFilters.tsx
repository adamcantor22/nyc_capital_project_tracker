import { useState } from 'react'
import type { FilterState } from '../filters/registry'
import { activeChips, valueLabel } from '../filters/chips'

interface Props {
  filters: FilterState
  onRemove(id: string, value: string): void
  /** Remove whole filters (a chip's ×). */
  onRemoveAll(ids: string[]): void
  onClear(): void
  /** Open the totals panel for what is filtered. */
  onTotals(): void
}

export default function ActiveFilters({ filters, onRemove, onRemoveAll, onClear, onTotals }: Props) {
  const [open, setOpen] = useState<string | null>(null)
  const chips = activeChips(filters)
  if (!chips.length) return null
  const shown = chips.find((c) => c.key === open)
  return (
    <div className="active-filters" role="region" aria-label="Active filters">
      <div className="af-row">
        <ul>
          {chips.map((c) => (
            <li key={c.key} className="fchip">
              <button type="button" className="fchip-main" aria-expanded={open === c.key} onClick={() => setOpen(open === c.key ? null : c.key)}
                title={c.values.map(({ id, v }) => valueLabel(id, v)).join(', ')}>
                <span className="fchip-k">{c.label}</span> {valueLabel(c.values[0].id, c.values[0].v)}
                {c.values.length > 1 && <span className="fchip-more">+{c.values.length - 1}</span>}
              </button>
              <button type="button" className="fchip-x" onClick={() => { onRemoveAll(c.ids); setOpen(null) }} aria-label={`Remove the ${c.label} filter`}>
                <svg viewBox="0 0 10 10" width="9" height="9" aria-hidden="true"><path d="M2 2l6 6M8 2L2 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" /></svg>
              </button>
            </li>
          ))}
        </ul>
        <div className="af-actions">
          <button type="button" className="totals" onClick={onTotals}>Totals</button>
          <button type="button" className="clear" onClick={() => { onClear(); setOpen(null) }}>Clear all</button>
        </div>
      </div>
      {shown && (
        <ul className="af-pop" aria-label={`${shown.label} values`}>
          {shown.values.map(({ id, v }) => (
            <li key={`${id}:${v}`}>
              <span>{valueLabel(id, v)}</span>
              <button type="button" className="fchip-x" onClick={() => { onRemove(id, v); if (shown.values.length === 1) setOpen(null) }} aria-label={`Remove ${valueLabel(id, v)}`}>
                <svg viewBox="0 0 10 10" width="9" height="9" aria-hidden="true"><path d="M2 2l6 6M8 2L2 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" /></svg>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

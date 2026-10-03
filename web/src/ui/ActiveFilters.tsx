import { filterById, type FilterState } from '../filters/registry'
import { districtName } from './format'
import { TIER_LABEL } from '../map/themes'
import { DEFAULT_FILTERS } from '../state/url'

interface Props {
  filters: FilterState
  onRemove(id: string, value: string): void
  onClear(): void
}

const valueLabel = (id: string, v: string) =>
  id === 'district' ? districtName(v) : id === 'tier' ? TIER_LABEL[v] : id === 'status' ? (v === 'current' ? 'In latest report' : 'No longer reported') : v

/** Every active filter as a removable chip, plus Clear all. Sticks to the top of the rail. */
export default function ActiveFilters({ filters, onRemove, onClear }: Props) {
  const chips = Object.entries(filters).flatMap(([id, vs]) =>
    (vs.join('|') === (DEFAULT_FILTERS[id] ?? []).join('|') ? [] : vs).map((v) => ({ id, v })))
  if (!chips.length) return null
  return (
    <div className="active-filters" role="region" aria-label="Active filters">
      <ul>
        {chips.map(({ id, v }) => (
          <li key={`${id}:${v}`}>
            <button type="button" className="fchip" onClick={() => onRemove(id, v)} aria-label={`Remove filter ${filterById[id]?.label}: ${valueLabel(id, v)}`}>
              <span className="fchip-k">{filterById[id]?.label}</span> {valueLabel(id, v)}
              <svg viewBox="0 0 10 10" width="9" height="9" aria-hidden="true"><path d="M2 2l6 6M8 2L2 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" /></svg>
            </button>
          </li>
        ))}
      </ul>
      <button type="button" className="clear" onClick={onClear}>Clear all</button>
    </div>
  )
}

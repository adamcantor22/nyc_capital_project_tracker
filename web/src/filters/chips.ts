import { filterById, type FilterState } from './registry'
import { districtName } from '../ui/format'
import { TIER_LABEL } from '../map/themes'
import { DEFAULT_FILTERS } from '../state/url'

const SHORT: Record<string, string> = { agency: 'Agency', sponsor: 'Sponsor', district: 'District', tier: 'Precision', size: 'Budget', schedule: 'Schedule' }
/** Filters shown as one chip: a theme is whole or split into subthemes, so they read as one choice. */
const CHIP_OF: Record<string, string> = { subtheme: 'theme' }

const PROGRAM_LABEL: Record<string, string> = { nyc_capital: 'City capital projects', sca: 'School construction (SCA)' }

export const valueLabel = (id: string, v: string) =>
  id === 'district' ? districtName(v) : id === 'tier' ? TIER_LABEL[v] : id === 'status' ? (v === 'current' ? 'In latest report' : 'No longer reported')
    : id === 'schedule' ? (v === 'yes' ? 'Has a schedule' : 'No schedule') : id === 'program' ? (PROGRAM_LABEL[v] ?? v) : v

/** The active filters, one chip per filter ("Theme Parks +2"). */
export function activeChips(filters: FilterState) {
  const chips = new Map<string, { ids: string[]; values: { id: string; v: string }[] }>()
  for (const [id, vs] of Object.entries(filters)) {
    if (!vs.length || vs.join('|') === (DEFAULT_FILTERS[id] ?? []).join('|')) continue
    const key = CHIP_OF[id] ?? id
    const c = chips.get(key) ?? { ids: [], values: [] }
    c.ids.push(id)
    c.values.push(...vs.map((v) => ({ id, v })))
    chips.set(key, c)
  }
  return [...chips].map(([key, c]) => ({ key, label: SHORT[key] ?? filterById[key]?.label ?? key, ...c }))
}


import { filterById, type FilterState } from '../filters/registry'

export interface UrlState {
  filters: FilterState
  selected: string | null
}

export const DEFAULT_FILTERS: FilterState = { status: ['current'] }

/** Filters become query parameters (?theme=Parks|Health&tier=A); the selected project is ?p=. */
export function parse(search: string): UrlState {
  const q = new URLSearchParams(search)
  const filters: FilterState = { ...DEFAULT_FILTERS }
  for (const [k, v] of q) {
    if (filterById[k]) filters[k] = v === '' ? [] : v.split('|')
  }
  return { filters, selected: q.get('p') }
}

export function serialize({ filters, selected }: UrlState): string {
  const q = new URLSearchParams()
  for (const [k, v] of Object.entries(filters)) {
    const dflt = DEFAULT_FILTERS[k] ?? []
    if (v.join('|') === dflt.join('|')) continue
    q.set(k, v.join('|'))
  }
  if (selected) q.set('p', selected)
  const s = q.toString()
  return s ? `?${s}` : ''
}

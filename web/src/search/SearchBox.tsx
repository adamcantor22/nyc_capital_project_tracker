import type MiniSearch from 'minisearch'
import { useEffect, useId, useMemo, useRef, useState } from 'react'
import type { Project } from '../data/types'
import { money } from '../measures/registry'
import { themeColor, TIER_LABEL } from '../map/themes'
import { matchPlaces, searchAddresses, type Place } from './index'

type Item = { type: 'place'; place: Place } | { type: 'project'; project: Project }

interface Props {
  index: MiniSearch | null
  byId: Map<string, Project>
  places: Place[]
  onPlace(p: Place): void
  onProject(id: string): void
  onLocate(): void
  locating: boolean
}

export default function SearchBox({ index, byId, places, onPlace, onProject, onLocate, locating }: Props) {
  const [q, setQ] = useState('')
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)
  const [addresses, setAddresses] = useState<Place[]>([])
  const listId = useId()
  const input = useRef<HTMLInputElement>(null)

  useEffect(() => {
    const ctl = new AbortController()
    const t = setTimeout(() => {
      searchAddresses(q, ctl.signal).then(setAddresses, () => setAddresses([]))
    }, 250)
    return () => {
      clearTimeout(t)
      ctl.abort()
    }
  }, [q])

  const items: Item[] = useMemo(() => {
    if (q.trim().length < 2) return []
    const ps = (index?.search(q) ?? []).slice(0, 8).flatMap((r) => {
      const p = byId.get(String(r.id))
      return p ? [{ type: 'project' as const, project: p }] : []
    })
    const pl = [...addresses, ...matchPlaces(places, q)].map((place) => ({ type: 'place' as const, place }))
    return [...pl, ...ps]
  }, [q, index, byId, places, addresses])

  function choose(it: Item) {
    if (it.type === 'place') onPlace(it.place)
    else onProject(it.project.id)
    setOpen(false)
    setQ(it.type === 'place' ? it.place.label : it.project.title)
    input.current?.blur()
  }

  function onKey(e: React.KeyboardEvent) {
    if (e.key === 'ArrowDown') { e.preventDefault(); setOpen(true); setActive((a) => Math.min(a + 1, items.length - 1)) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)) }
    else if (e.key === 'Enter' && items[active]) { e.preventDefault(); choose(items[active]) }
    else if (e.key === 'Escape') { setOpen(false) }
  }

  const showList = open && q.trim().length >= 2
  return (
    <div className="search">
      <div className="search-row">
        <label htmlFor={`${listId}-input`} className="visually-hidden">Search an address, neighborhood or project</label>
        <input
          ref={input}
          id={`${listId}-input`}
          type="search"
          role="combobox"
          aria-expanded={showList}
          aria-controls={listId}
          aria-activedescendant={showList && items[active] ? `${listId}-${active}` : undefined}
          aria-autocomplete="list"
          autoComplete="off"
          placeholder="Address, neighborhood or project"
          value={q}
          onChange={(e) => { setQ(e.target.value); setOpen(true); setActive(0) }}
          onFocus={() => setOpen(true)}
          onBlur={() => setTimeout(() => setOpen(false), 120)}
          onKeyDown={onKey}
        />
        <button type="button" className="locate" onClick={onLocate} disabled={locating} aria-label="Show projects near me" title="Near me">
          <svg viewBox="0 0 20 20" width="18" height="18" aria-hidden="true">
            <circle cx="10" cy="10" r="4.2" fill="none" stroke="currentColor" strokeWidth="1.6" />
            <circle cx="10" cy="10" r="1.4" fill="currentColor" />
            <path d="M10 1.5v3M10 15.5v3M1.5 10h3M15.5 10h3" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
          </svg>
        </button>
      </div>
      {showList && (
        <ul id={listId} role="listbox" className="results">
          {items.length === 0 && <li className="noresult">No matches. Try a street address with a house number, a neighborhood, or a project ID.</li>}
          {items.map((it, i) => (
            <li
              key={it.type === 'place' ? `pl-${it.place.label}-${i}` : it.project.id}
              id={`${listId}-${i}`}
              role="option"
              aria-selected={i === active}
              className="result"
              onMouseDown={(e) => { e.preventDefault(); choose(it) }}
              onMouseEnter={() => setActive(i)}
            >
              {it.type === 'place' ? (
                <>
                  <span className="r-icon place" aria-hidden="true" />
                  <span className="r-title">{it.place.label}</span>
                  <span className="r-meta">{it.place.kind === 'address' ? 'Address' : 'Neighborhood'} · {it.place.detail}</span>
                </>
              ) : (
                <>
                  <span className="r-icon" style={{ background: themeColor(it.project.theme) }} aria-hidden="true" />
                  <span className="r-title">{it.project.title}</span>
                  <span className="r-meta">{money(it.project.budget)} · {it.project.agencies.join(', ')} · {TIER_LABEL[it.project.tier]}</span>
                </>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

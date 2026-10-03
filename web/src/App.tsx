import { useCallback, useEffect, useMemo, useState } from 'react'
import { loadAll, loadAreas, type Areas } from './data/load'
import type { Manifest, Project } from './data/types'
import { applyFilters, type FilterState } from './filters/registry'
import MapView, { type Bounds, type Focus } from './map/MapView'
import { buildIndex, neighborhoodPlaces, type Place } from './search'
import SearchBox from './search/SearchBox'
import { money } from './measures/registry'
import Detail from './detail/Detail'
import Legend from './ui/Legend'
import MoreFilters from './ui/MoreFilters'
import ProjectList from './ui/ProjectList'
import { DEFAULT_FILTERS, parse, serialize } from './state/url'

function toggle(list: string[] = [], values: string[]): string[] {
  const allOn = values.every((v) => list.includes(v))
  return allOn ? list.filter((v) => !values.includes(v)) : [...new Set([...list, ...values])]
}

function snapshotLabel(p: number) {
  const months = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
  return `${months[(p % 100) - 1]} ${Math.floor(p / 100)}`
}

export default function App() {
  const [data, setData] = useState<{ manifest: Manifest; projects: Project[] } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const initial = useMemo(() => parse(location.search), [])
  const [filters, setFilters] = useState<FilterState>(initial.filters)
  const [hoverTheme, setHoverTheme] = useState<string | null>(null)
  const [hoverTier, setHoverTier] = useState<string | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(initial.selected)
  const [view, setView] = useState<Bounds | null>(null)
  const [areas, setAreas] = useState<Areas | null>(null)
  const [focus, setFocus] = useState<Focus | null>(null)
  const [locating, setLocating] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const [seen, setSeen] = useState<Set<string>>(() => {
    try {
      return new Set(JSON.parse(localStorage.getItem('seen') ?? '[]') as string[])
    } catch {
      return new Set()
    }
  })

  // Keep the URL in step with the view, so any state can be shared or bookmarked.
  useEffect(() => {
    const q = serialize({ filters, selected: selectedId })
    if (q !== location.search) history.replaceState(null, '', `${location.pathname}${q}`)
  }, [filters, selectedId])
  useEffect(() => {
    const onPop = () => {
      const s = parse(location.search)
      setFilters(s.filters)
      setSelectedId(s.selected)
    }
    addEventListener('popstate', onPop)
    return () => removeEventListener('popstate', onPop)
  }, [])

  useEffect(() => {
    loadAll().then(setData, (e: Error) => setError(e.message))
    loadAreas().then(setAreas, () => setNotice('Area boundaries could not be loaded; coarse locations are not shaded.'))
  }, [])

  const all = useMemo(() => data?.projects ?? [], [data])
  const filtered = useMemo(() => applyFilters(all, filters), [all, filters])
  const themeBase = useMemo(() => applyFilters(all, { ...filters, theme: [] }), [all, filters])
  const tierBase = useMemo(() => applyFilters(all, { ...filters, tier: [] }), [all, filters])
  const allThemes = useMemo(() => [...new Set(all.map((p) => p.theme))].sort(), [all])
  const inView = useMemo(
    () => (view ? filtered.filter((p) => p.onMap && p.lon! >= view.w && p.lon! <= view.e && p.lat! >= view.s && p.lat! <= view.n) : []),
    [filtered, view],
  )
  const index = useMemo(() => (data ? buildIndex(filtered) : null), [data, filtered])
  const byId = useMemo(() => new Map(all.map((p) => [p.id, p])), [all])
  const places = useMemo(() => (areas ? neighborhoodPlaces(areas.neighborhoods) : []), [areas])
  const unplaced = useMemo(() => filtered.filter((p) => !p.onMap), [filtered])

  const onToggleTheme = useCallback((ts: string[]) => setFilters((f) => ({ ...f, theme: toggle(f.theme, ts) })), [])
  const select = useCallback(
    (id: string | null) => {
      setSelectedId(id)
      if (id) {
        setSeen((s) => {
          const next = new Set(s).add(id)
          try {
            localStorage.setItem('seen', JSON.stringify([...next].slice(-2000)))
          } catch {
            /* private mode: the change marks just reset next visit */
          }
          return next
        })
      }
      const p = id ? byId.get(id) : undefined
      if (p?.onMap) setFocus({ lon: p.lon!, lat: p.lat!, zoom: 15, key: Date.now(), mark: null })
    },
    [byId],
  )
  const onPlace = useCallback((pl: Place) => {
    setNotice(null)
    setFocus({ lon: pl.lon, lat: pl.lat, zoom: pl.zoom, key: Date.now(), mark: pl.kind === 'address' ? 'address' : null })
  }, [])
  const onLocate = useCallback(() => {
    if (!navigator.geolocation) return setNotice('This browser cannot share its location.')
    setLocating(true)
    navigator.geolocation.getCurrentPosition(
      ({ coords }) => {
        setLocating(false)
        const inNyc = coords.latitude > 40.47 && coords.latitude < 40.93 && coords.longitude > -74.27 && coords.longitude < -73.68
        if (!inNyc) return setNotice('You appear to be outside New York City, so the map stays on the city.')
        setNotice(null)
        setFocus({ lon: coords.longitude, lat: coords.latitude, zoom: 15, key: Date.now(), mark: 'me' })
      },
      () => {
        setLocating(false)
        setNotice('Location was not shared. Search an address instead.')
      },
      { timeout: 10000 },
    )
  }, [])
  // A change mark stays lit on projects whose budget moved in the latest report until the visitor opens them.
  const isLit = useCallback(
    (p: Project) => p.status === 'current' && !!p.budgetChange && p.lastReported === data?.manifest.latest_snapshot && !seen.has(p.id),
    [seen, data],
  )
  const selected = selectedId ? byId.get(selectedId) : undefined
  const onFilter = useCallback((id: string, values: string[]) => setFilters((f) => ({ ...f, [id]: values })), [])
  const onToggleTier = useCallback((t: string) => setFilters((f) => ({ ...f, tier: toggle(f.tier, [t]) })), [])
  const active = Object.entries(filters).some(([k, v]) => v.length && !(k === 'status' && v.join() === 'current'))

  if (error) {
    return (
      <div className="state-screen" role="alert">
        <p>The project data could not be loaded.</p>
        <p className="detail">{error}</p>
        <button type="button" onClick={() => location.reload()}>Try again</button>
      </div>
    )
  }

  const placed = filtered.filter((p) => p.onMap)
  const budget = filtered.reduce((s, p) => s + p.budget, 0)
  const placedBudget = placed.reduce((s, p) => s + p.budget, 0)
  const pct = (a: number, b: number) => (b ? Math.round((100 * a) / b) : 0)

  return (
    <div className="shell">
      <aside className="rail" aria-label="Projects and key">
        <header className="masthead">
          <h1>NYC Capital Projects</h1>
          <p className="sub">
            {data ? (
              <>
                {filtered.length.toLocaleString()} projects · {money(budget)} · as reported {snapshotLabel(data.manifest.latest_snapshot)}
              </>
            ) : (
              'Loading the latest report…'
            )}
          </p>
        </header>
        {data ? (
          <>
            <SearchBox index={index} byId={byId} places={places} onPlace={onPlace} onProject={select} onLocate={onLocate} locating={locating} />
            {notice && <p className="notice" role="status">{notice}</p>}
            <Legend
              themeBase={themeBase}
              tierBase={tierBase}
              allThemes={allThemes}
              filters={filters}
              onToggleTheme={onToggleTheme}
              onToggleTier={onToggleTier}
              onHoverTheme={setHoverTheme}
              onHoverTier={setHoverTier}
            />
            <p className="coverage">
              The map pins {pct(placed.length, filtered.length)}% of these projects ({pct(placedBudget, budget)}% of the money). The rest are known only to an area (tap Neighborhood, District or Borough in the key to shade them) or listed below.
            </p>
            <MoreFilters projects={all} filters={filters} onChange={onFilter} />
            {active && (
              <button type="button" className="clear" onClick={() => setFilters(DEFAULT_FILTERS)}>
                Clear filters
              </button>
            )}
            <ProjectList
              title="On the map here"
              projects={inView}
              selectedId={selectedId}
              onSelect={select}
              isLit={isLit}
              empty="No pinned projects in this view. Zoom out, move the map, or clear a filter."
            />
            <ProjectList
              title="Citywide or without a location"
              projects={unplaced.filter((p) => p.tier === 'Unplaced')}
              selectedId={selectedId}
              onSelect={select}
              isLit={isLit}
              limit={15}
              empty="None under these filters."
            />
          </>
        ) : (
          <div className="skeleton" aria-hidden="true">
            <span /><span /><span /><span />
          </div>
        )}
      </aside>
      <main className="stage">
        <MapView
          projects={filtered}
          areas={areas}
          focus={focus}
          highlightTheme={hoverTheme}
          highlightTier={hoverTier}
          shownTiers={filters.tier ?? []}
          selectedId={selectedId}
          onSelect={select}
          onView={setView}
        />
        {selected && data && <Detail key={selected.id} project={selected} manifest={data.manifest} onClose={() => setSelectedId(null)} />}
      </main>
    </div>
  )
}

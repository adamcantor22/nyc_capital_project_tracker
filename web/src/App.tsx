import { useCallback, useEffect, useMemo, useState } from 'react'
import { loadAll } from './data/load'
import type { Manifest, Project } from './data/types'
import { applyFilters, type FilterState } from './filters/registry'
import MapView, { type Bounds } from './map/MapView'
import { money } from './measures/registry'
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
  const unplaced = useMemo(() => filtered.filter((p) => !p.onMap), [filtered])

  const onToggleTheme = useCallback((ts: string[]) => setFilters((f) => ({ ...f, theme: toggle(f.theme, ts) })), [])
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
              The map pins {pct(placed.length, filtered.length)}% of these projects ({pct(placedBudget, budget)}% of the money). The rest are shaded by area or listed below.
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
              onSelect={setSelectedId}
              empty="No pinned projects in this view. Zoom out, move the map, or clear a filter."
            />
            <ProjectList
              title="Citywide or without a location"
              projects={unplaced.filter((p) => p.tier === 'Unplaced')}
              selectedId={selectedId}
              onSelect={setSelectedId}
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
          highlightTheme={hoverTheme}
          highlightTier={hoverTier}
          selectedId={selectedId}
          onSelect={setSelectedId}
          onView={setView}
        />
      </main>
    </div>
  )
}

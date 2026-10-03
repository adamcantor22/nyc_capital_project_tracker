import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { loadAll, loadAreas, loadSites, type Areas } from './data/load'
import { aggregateAreas, type Level, type Site } from './areas/aggregate'
import AreaControls from './areas/AreaControls'
import { areaName, buildAreaLayer } from './areas/layer'
import { areaMeasureById } from './areas/measures'
import type { Manifest, Project } from './data/types'
import { applyFilters, pick, pickSub, pickTheme, subKey, type FilterState } from './filters/registry'
import MapView, { type Bounds, type Focus } from './map/MapView'
import { buildIndex, neighborhoodPlaces, type Place } from './search'
import SearchBox from './search/SearchBox'
import { money } from './measures/registry'
import Detail from './detail/Detail'
import ActiveFilters from './ui/ActiveFilters'
import { activeChips, valueLabel } from './filters/chips'
import Legend from './ui/Legend'
import ThemeStrip from './ui/ThemeStrip'
import { usePhone } from './ui/usePhone'
import Selection from './ui/Selection'
import { inBox, type Box } from './measures/aggregate'
import MoreFilters from './ui/MoreFilters'
import ProjectList from './ui/ProjectList'
import { DEFAULT_FILTERS, parse, serialize } from './state/url'
import { districtName } from './ui/format'


const BORO: Record<string, string> = { '1': 'Manhattan', '2': 'Bronx', '3': 'Brooklyn', '4': 'Queens', '5': 'Staten Island' }
const BORO_CODE: Record<string, string> = { MN: '1', BX: '2', BK: '3', QN: '4', SI: '5' }
function geomCoords(g: import('geojson').Geometry): number[][] {
  return g.type === 'Polygon' ? g.coordinates.flat() : g.type === 'MultiPolygon' ? g.coordinates.flat(2) : []
}
function bbox(cs: number[][]): Bounds | null {
  if (!cs.length) return null
  const b = { w: Infinity, e: -Infinity, s: Infinity, n: -Infinity }
  for (const [x, y] of cs) Object.assign(b, { w: Math.min(b.w, x), e: Math.max(b.e, x), s: Math.min(b.s, y), n: Math.max(b.n, y) })
  return b
}
const isDefault = (f: FilterState) => serialize({ filters: f, selected: null }) === ''

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
  const [sites, setSites] = useState<Map<string, Site[]> | null>(null)
  const [areaLevel, setAreaLevel] = useState<Level | null>((initial.view as Level) ?? null)
  const [areaMeasure, setAreaMeasure] = useState(initial.measure && areaMeasureById[initial.measure] ? initial.measure : 'budget')
  const [selectedArea, setSelectedArea] = useState<string | null>(null)
  const [selecting, setSelecting] = useState(false)
  const phone = usePhone()
  // Phone: the rail is a sheet over the map, peeking, half or nearly full height.
  const [sheet, setSheet] = useState<'peek' | 'half' | 'full'>('peek')
  const drag = useRef<number | null>(null)
  const [area, setArea] = useState<Box | null>(null)
  // Totals for one value, opened from a link in the project panel ("all DEP projects").
  const [summary, setSummary] = useState<{ filters: FilterState; title: string } | null>(null)
  const [seen, setSeen] = useState<Set<string>>(() => {
    try {
      return new Set(JSON.parse(localStorage.getItem('seen') ?? '[]') as string[])
    } catch {
      return new Set()
    }
  })

  // Keep the URL in step with the view, so any state can be shared or bookmarked.
  useEffect(() => {
    const q = serialize({ filters, selected: selectedId, view: areaLevel, measure: areaMeasure })
    if (q !== location.search) history.replaceState(null, '', `${location.pathname}${q}`)
  }, [filters, selectedId, areaLevel, areaMeasure])
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
    loadAll().then((d) => {
      setData(d)
      // A shared link to a project opens on it.
      const p = initial.selected ? d.projects.find((x) => x.id === initial.selected) : undefined
      if (p?.onMap) setFocus({ lon: p.lon!, lat: p.lat!, zoom: 15, key: Date.now(), mark: null })
      loadSites(d.manifest).then(setSites, () => setNotice('Site data could not be loaded; area totals are unavailable.'))
    }, (e: Error) => setError(e.message))
    loadAreas().then(setAreas, () => setNotice('Area boundaries could not be loaded; coarse locations are not shaded.'))
  }, [initial.selected])

  const all = useMemo(() => data?.projects ?? [], [data])
  const filtered = useMemo(() => applyFilters(all, filters), [all, filters])
  const themeBase = useMemo(() => applyFilters(all, { ...filters, theme: [], subtheme: [] }), [all, filters])
  const tierBase = useMemo(() => applyFilters(all, { ...filters, tier: [] }), [all, filters])
  const allThemes = useMemo(() => [...new Set(all.map((p) => p.theme))].sort(), [all])
  const subsOf = useMemo(() => {
    const m = new Map<string, Set<string>>()
    for (const p of all) if (p.subtheme) m.set(p.theme, new Set())
    for (const p of all) m.get(p.theme)?.add(subKey(p))
    return (t: string) => [...(m.get(t) ?? [])]
  }, [all])
  const inView = useMemo(
    () => (view ? filtered.filter((p) => p.onMap && p.lon! >= view.w && p.lon! <= view.e && p.lat! >= view.s && p.lat! <= view.n) : []),
    [filtered, view],
  )
  const index = useMemo(() => (data ? buildIndex(filtered) : null), [data, filtered])
  const byId = useMemo(() => new Map(all.map((p) => [p.id, p])), [all])
  const places = useMemo(() => (areas ? neighborhoodPlaces(areas.neighborhoods) : []), [areas])
  const unplaced = useMemo(() => filtered.filter((p) => !p.onMap), [filtered])

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
  const areaProjects = useMemo(() => (area ? inBox(filtered, area) : []), [area, filtered])
  const areaStats = useMemo(() => (areaLevel && sites ? aggregateAreas(areaLevel, filtered, sites) : null), [areaLevel, sites, filtered])
  const areaLayer = useMemo(() => {
    if (!areaLevel || !areaStats || !areas) return null
    return { level: areaLevel, ...buildAreaLayer(areaLevel, areas, areaStats, areaMeasureById[areaMeasure]) }
  }, [areaLevel, areaStats, areas, areaMeasure])
  const onAreaClick = useCallback((key: string | null) => {
    setSelectedArea(key)
    if (key) setArea(null)
  }, [])
  const onAreaLevel = useCallback((l: Level | null) => {
    setAreaLevel(l)
    setSelectedArea(null)
  }, [])
  const totals = useMemo(() => {
    const theme = new Map<string, number>()
    const agency = new Map<string, number>()
    let sum = 0
    for (const p of all) {
      if (p.status !== 'current') continue
      sum += p.budget
      theme.set(p.theme, (theme.get(p.theme) ?? 0) + p.budget)
      for (const a of p.agencies) agency.set(a, (agency.get(a) ?? 0) + p.budget)
    }
    return { all: sum, n: all.filter((p) => p.status === 'current').length, theme, agency }
  }, [all])
  const onSummary = useCallback((id: string, v: string) => {
    const next = { ...DEFAULT_FILTERS, [id]: [v] }
    setFilters(next)
    setSummary({ filters: next, title: id === 'district' ? `Community district ${districtName(v)}` : id === 'sponsor' ? `Sponsored by ${v}` : id === 'agency' ? `Managed by ${v}` : v })
    setSelectedId(null)
    setArea(null)
    // Zoom to the place itself, or else to everything it matches that has a pin.
    const level = id === 'district' ? 'districts' : id === 'borough' ? 'boroughs' : null
    const shape = level && areas?.[level].features.find((f) => String(f.properties?.[level === 'districts' ? 'district' : 'borough']) === v)
    const bounds = shape ? bbox(geomCoords(shape.geometry)) : bbox(applyFilters(all, next).filter((p) => p.onMap && !p.outsideNyc).map((p) => [p.lon!, p.lat!]))
    if (bounds) setFocus({ lon: 0, lat: 0, zoom: 0, key: Date.now(), mark: null, bounds })
  }, [areas, all])
  const summaryOn = !!summary && serialize({ filters, selected: null }) === serialize({ filters: summary.filters, selected: null })
  const onTotals = useCallback(() => {
    const title = activeChips(filters).map((c) => `${valueLabel(c.values[0].id, c.values[0].v)}${c.values.length > 1 ? ` +${c.values.length - 1}` : ''}`).join(' · ')
    setSummary({ filters, title: title || 'All projects' })
    setSelectedId(null)
    setArea(null)
  }, [filters])
  const filteredBudget = useMemo(() => filtered.reduce((s, p) => s + p.budget, 0), [filtered])
  const cityShare = useMemo(() => [{ label: isDefault(filters) ? 'the city' : 'the city (these filters)', whole: filteredBudget }], [filters, filteredBudget])
  const areaPanel = useMemo(() => {
    if (!areaLevel || !selectedArea || !areaStats || !sites) return null
    const st = areaStats.get(selectedArea)
    if (!st) return null
    // Wholes this area is a slice of, each counted by its own level's precision rule.
    const shares: { label: string; whole: number }[] = []
    const boro = areaLevel === 'districts' ? BORO[selectedArea[0]]
      : areaLevel === 'neighborhoods' ? areas?.neighborhoods.features.find((f) => f.properties?.name === selectedArea)?.properties?.borough : null
    if (areaLevel === 'neighborhoods') {
      const nta = areas?.neighborhoods.features.find((f) => f.properties?.name === selectedArea)?.properties?.nta as string | undefined
      const cd = nta ? `${BORO_CODE[nta.slice(0, 2)]}${nta.slice(2, 4)}` : null
      const whole = cd ? aggregateAreas('districts', filtered, sites).get(String(Number(cd)))?.budget : undefined
      if (cd && whole) shares.push({ label: districtName(String(Number(cd))), whole })
    }
    if (boro) {
      const whole = aggregateAreas('boroughs', filtered, sites).get(boro)?.budget
      if (whole) shares.push({ label: boro, whole })
    }
    return { title: areaName(areaLevel, selectedArea), weights: st.weights, projects: filtered.filter((p) => st.weights.has(p.id)), shares: [...shares, ...cityShare] }
  }, [areaLevel, selectedArea, areaStats, filtered, sites, areas, cityShare])
  const onArea = useCallback((b: Box | null) => {
    // A new box is the latest question: its totals replace any open project, area or filter totals.
    setArea(b)
    setSelecting(false)
    setSelectedId(null)
    setSelectedArea(null)
    setSummary(null)
  }, [])
  useEffect(() => {
    if (!selecting) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setSelecting(false)
    addEventListener('keydown', onKey)
    return () => removeEventListener('keydown', onKey)
  }, [selecting])
  const onFilter = useCallback((id: string, values: string[]) => setFilters((f) => ({ ...f, [id]: values })), [])
  const onPick = useCallback((id: string, values: string[], add: boolean) => setFilters((f) => ({ ...f, [id]: pick(f[id], values, add) })), [])
  const onPickTheme = useCallback((themes: string[], add: boolean) => setFilters((f) => pickTheme(f, themes, add, subsOf)), [subsOf])
  const onPickSub = useCallback((theme: string, sub: string, add: boolean) => setFilters((f) => pickSub(f, theme, sub, subsOf(theme), add)), [subsOf])

  const panelOpen = !!selectedId || summaryOn || !!areaPanel || !!area
  // An open project or totals panel is its own sheet; the rail slides away beneath it.
  const sheetShown = panelOpen ? 'hidden' : sheet
  const SHEETS = ['peek', 'half', 'full'] as const
  const step = (d: number) => setSheet((s) => SHEETS[Math.max(0, Math.min(2, SHEETS.indexOf(s) + d))])

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

  const searchBox = <SearchBox index={index} byId={byId} places={places} onPlace={onPlace} onProject={select} onLocate={onLocate} locating={locating} />
  const nFilters = activeChips(filters).length

  return (
    <div className="shell">
      <aside className={`rail${phone ? ` sheet-${sheetShown}` : ''}`} aria-label="Projects and key">
        {phone && (
          <button type="button" className="sheet-handle" aria-label={sheetShown === 'full' ? 'Lower the panel' : 'Raise the panel'}
            onPointerDown={(e) => { drag.current = e.clientY; e.currentTarget.setPointerCapture(e.pointerId) }}
            onPointerUp={(e) => {
              if (drag.current === null) return
              const dy = e.clientY - drag.current
              drag.current = null
              if (Math.abs(dy) < 10) setSheet((s) => (s === 'full' ? 'peek' : s === 'peek' ? 'half' : 'full'))
              else step(dy < 0 ? (dy < -200 ? 2 : 1) : (dy > 200 ? -2 : -1))
            }}
            onClick={(e) => { if (e.detail === 0) setSheet((s) => (s === 'full' ? 'peek' : s === 'peek' ? 'half' : 'full')) }}>
            <span />
          </button>
        )}
        <header className="masthead" onClick={phone && sheetShown === 'peek' ? () => setSheet('half') : undefined}>
          <h1>NYC Capital Projects</h1>
          <p className="sub">
            {data ? (
              <>
                {filtered.length.toLocaleString()} projects · {money(budget)} · as reported {snapshotLabel(data.manifest.latest_snapshot)}
                {phone && nFilters > 0 && <span className="peek-filters"> · {nFilters} filter{nFilters === 1 ? '' : 's'}</span>}
              </>
            ) : (
              'Loading the latest report…'
            )}
          </p>
        </header>
        {data ? (
          <>
            <ActiveFilters
              filters={filters}
              onRemove={(id, v) => setFilters((f) => ({ ...f, [id]: (f[id] ?? []).filter((x) => x !== v) }))}
              onRemoveAll={(ids) => setFilters((f) => ({ ...f, ...Object.fromEntries(ids.map((id) => [id, DEFAULT_FILTERS[id] ?? []])) }))}
              onClear={() => setFilters(DEFAULT_FILTERS)}
              onTotals={onTotals}
            />
            {!phone && searchBox}
            {notice && !phone && <p className="notice" role="status">{notice}</p>}
            <Legend
              themeBase={themeBase}
              tierBase={tierBase}
              allThemes={allThemes}
              filters={filters}
              subsOf={subsOf}
              onPick={onPick}
              onPickTheme={onPickTheme}
              onPickSub={onPickSub}
              areaLevel={areaLevel}
              onAreaLevel={onAreaLevel}
              onHoverTheme={setHoverTheme}
              onHoverTier={setHoverTier}
            />
            <p className="coverage">
              The map pins {pct(placed.length, filtered.length)}% of these projects ({pct(placedBudget, budget)}% of the money). The rest are known only to an area (tap Neighborhood, District or Borough in the key, or the switch on the map, for totals by area) or listed below.
            </p>
            <MoreFilters projects={all} filters={filters} onChange={onFilter} />
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
        {phone && data && (
          <div className="phone-top">
            {searchBox}
            <ThemeStrip allThemes={allThemes} filters={filters} subsOf={subsOf} onPickTheme={onPickTheme} />
            {notice && <p className="notice" role="status">{notice}</p>}
          </div>
        )}
        <MapView
          projects={filtered}
          focus={focus}
          highlightTheme={hoverTheme}
          highlightTier={hoverTier}
          areaLayer={areaLayer}
          selectedArea={selectedArea}
          onAreaClick={onAreaClick}
          selectedId={selectedId}
          onSelect={select}
          onView={setView}
          selecting={selecting}
          area={area}
          onArea={onArea}
        />
        <AreaControls level={areaLevel} measure={areaMeasure} max={areaLayer?.max ?? 0} min={areaLayer?.min ?? 0}
          onLevel={onAreaLevel} onMeasure={setAreaMeasure} compact={phone}>
          <div className="map-tools">
            <button type="button" className={`tool${selecting ? ' on' : ''}`} aria-pressed={selecting} onClick={() => setSelecting((v) => !v)}>
              <svg viewBox="0 0 20 20" width="16" height="16" aria-hidden="true"><rect x="3" y="4" width="14" height="12" rx="1" fill="none" stroke="currentColor" strokeWidth="1.6" strokeDasharray="3 2" /></svg>
              {selecting ? 'Drag a box on the map' : phone ? 'Select' : 'Select an area'}
            </button>
            {selecting && <button type="button" className="tool" onClick={() => setSelecting(false)}>Cancel</button>}
          </div>
        </AreaControls>
        {summaryOn && !selected && (
          <Selection title={summary!.title} projects={filtered} shares={[{ label: 'all current capital money', whole: totals.all }]}
            note="Every project in the latest report, pinned or not."
            onOpen={select} onClear={() => setSummary(null)} />
        )}
        {areaPanel && !selected && !summaryOn && (
          <Selection title={areaPanel.title} projects={areaPanel.projects} weights={areaPanel.weights}
            note={areaLevel === 'boroughs' ? 'Every project with this borough.' : 'Projects located here at this precision or better; multi-site projects count their share.'}
            shares={areaPanel.shares} onOpen={select} onClear={() => setSelectedArea(null)} />
        )}
        {area && !selected && (
          <Selection title="This area" projects={areaProjects} shares={cityShare}
            note="Pinned projects only (exact sites and matched facilities); projects known only to a district or borough are not counted."
            onOpen={select} onClear={() => setArea(null)} />
        )}
        {selected && data && <Detail key={selected.id} project={selected} manifest={data.manifest} onClose={() => setSelectedId(null)} onFilter={onSummary} totals={totals} />}
      </main>
    </div>
  )
}

import type { FeatureCollection, Geometry, Point } from 'geojson'
import { useEffect, useMemo, useRef, useState } from 'react'
import type { Site } from '../areas/aggregate'
import { fetchJson, loadAll, loadSites } from '../data/load'
import { fromStoryRows, type StoryRow } from './data'
import type { Manifest, Project } from '../data/types'
import { MONTHS, periodLabel } from '../ui/format'
import {
  boroughJails, buildings, districtMoney, jumps, type Jump, largestPlaced, leadProjectIn, megaProject, servingLeadIn, money, perResident, PROGRAMS, programTotals, tintOf,
  PEOPLE, quarterLabel, RAMP, siteDots, siteGroups, statementsFor, type AreaCount, type MegaPoint, type PopulationRow, type Spot, type Statement,
} from './plates'
import StoryMap, { type View } from './StoryMap'

type PlateId = 'builders' | 'jails' | 'resident' | 'psa' | 'map'
const PLATES: { id: PlateId; n: number; title: string }[] = [
  { id: 'builders', n: 1, title: 'Three builders' },
  { id: 'jails', n: 2, title: 'The jails' },
  { id: 'resident', n: 3, title: 'Per resident' },
  { id: 'psa', n: 4, title: 'Penn Station Access' },
  { id: 'map', n: 5, title: 'The map' },
]
const n = (id: PlateId) => PLATES.find((p) => p.id === id)!.n
const RESUME_KEY = 'story-plate'
const NONE: Spot[] = []
const TOOL = `${import.meta.env.BASE_URL}map/`

interface Data {
  manifest: Manifest
  projects: Project[]
  sites: Map<string, Site[]>
  districts: FeatureCollection
  boroughs: FeatureCollection | null
  counts: Record<string, AreaCount[]>
  population: PopulationRow[]
  mega: MegaPoint[]
  statements: Statement[]
  rail: FeatureCollection | null
  reach: StationReach[]
  series: SeriesRow[]
}

/** One row of story_series.json: a charted project's budget in one report (OMB's editions, then the dashboard's). */
interface SeriesRow { id: string; period: number; budget: number; source: string; rule: string }

/** One row of station_reach.json (pipeline/rail.py): residents within 800 m of a new station, an estimate. */
interface StationReach { mega_project: string; no: number; station: string; lon: number; lat: number; radius_m: number; residents: number }

async function load(): Promise<Data> {
  const manifest = await fetchJson<Manifest>('manifest.json')
  // One slim file for the story (story_projects.json); a data release without it falls back to the full files.
  const main = manifest.files['story_projects.json']
    ? fetchJson<StoryRow[]>('story_projects.json').then(fromStoryRows)
    : Promise.all([loadAll(), loadSites(manifest), fetchJson<Record<string, AreaCount[]>>('area_counts.json')])
      .then(([all, sites, counts]) => ({ projects: all.projects, sites, counts }))
  // The borough outlines only draw the desktop key map; a phone skips them.
  const wide = !window.matchMedia(PHONE).matches
  const [{ projects, sites, counts }, districts, boroughs, population, mega, statements, rail, reach, series] = await Promise.all([
    main,
    fetchJson<FeatureCollection>('areas/districts.geojson'),
    wide ? fetchJson<FeatureCollection>('areas/boroughs.geojson') : Promise.resolve(null),
    fetchJson<PopulationRow[]>('area_population.json'),
    fetchJson<MegaPoint[]>('mta_mega_series.json'),
    // Absent from data releases before they were exported: the plates then leave these out.
    fetchJson<Statement[]>('mta_mega_statements.json').catch(() => [] as Statement[]),
    fetchJson<FeatureCollection>('rail_lines.geojson').catch(() => null),
    fetchJson<StationReach[]>('station_reach.json').catch(() => [] as StationReach[]),
    fetchJson<SeriesRow[]>('story_series.json').catch(() => [] as SeriesRow[]),
  ])
  return { manifest, projects, sites, districts, boroughs, counts, population, mega, statements, rail, reach, series }
}

const readResume = (): PlateId | null => {
  try { return (localStorage.getItem(RESUME_KEY) as PlateId | null) } catch { return null }
}
const writeResume = (id: PlateId) => {
  try { localStorage.setItem(RESUME_KEY, id) } catch { /* storage blocked: resume is a convenience */ }
}

const PHONE = '(max-width: 760px)'

function usePhone() {
  const [phone, setPhone] = useState(() => window.matchMedia(PHONE).matches)
  useEffect(() => {
    const m = window.matchMedia(PHONE)
    const on = () => setPhone(m.matches)
    m.addEventListener('change', on)
    return () => m.removeEventListener('change', on)
  }, [])
  return phone
}

export default function Story() {
  const [data, setData] = useState<Data | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [active, setActive] = useState<PlateId>('builders')
  const [stopped] = useState<PlateId | null>(readResume)
  const [step, setStep] = useState<'where' | 'serves'>('where')
  const [focused, setFocused] = useState<{ plate: PlateId; spot: Spot } | null>(null)
  const [hot, setHotState] = useState<string | null>(null)
  // On a touch screen a tap fires mouseenter with no mouseleave, which would leave a marker stuck emphasised.
  const setHot = (id: string | null) => { if (!id || window.matchMedia('(hover: hover)').matches) setHotState(id) }
  const [highlight, setHighlight] = useState<string | null>(null)
  const phone = usePhone()
  const column = useRef<HTMLElement>(null)

  useEffect(() => { load().then(setData, (e: Error) => setError(e.message)) }, [])
  useEffect(() => { if (active !== 'builders') writeResume(active) }, [active])
  const focus = focused?.plate === active ? focused.spot : null
  const setFocus = (s: Spot | null) => setFocused(s ? { plate: active, spot: s } : null)

  // A link to a plate (#plate-resident) opens on it once the plates exist.
  useEffect(() => {
    if (data && location.hash.startsWith('#plate-')) document.getElementById(location.hash.slice(1))?.scrollIntoView()
  }, [data])

  // Turning to another plate lets go of whatever the last one had chosen or emphasised, so a plate never opens with a
  // marker still selected from an earlier visit, whatever order the reader tapped things in.
  const shown = useRef<PlateId>('builders')
  const turnTo = (id: PlateId) => {
    if (id === shown.current) return
    shown.current = id
    setActive(id); setFocused(null); setHotState(null); setHighlight(null)
  }

  // The plate being read: on a desktop the one whose top has crossed the middle of the window; on a phone, where the
  // plates scroll in their own pane under the map, the one whose top has reached the top of that pane.
  useEffect(() => {
    if (!data) return
    const els = PLATES.map((p) => document.getElementById(`plate-${p.id}`)).filter((e): e is HTMLElement => !!e)
    const io = new IntersectionObserver((entries) => {
      for (const e of entries) if (e.isIntersecting) turnTo(e.target.id.replace('plate-', '') as PlateId)
    }, phone ? { root: column.current, rootMargin: '-12% 0px -80% 0px' } : { rootMargin: '-45% 0px -50% 0px' })
    els.forEach((e) => io.observe(e))
    return () => io.disconnect()
  }, [data, phone])

  const computed = useMemo(() => {
    if (!data) return null
    const names = new Map(data.districts.features.map((f) => [String(f.properties?.district), String(f.properties?.name ?? f.properties?.district)]))
    const totals = programTotals(data.projects)
    const spots = largestPlaced(data.projects, data.sites)
    const dm = districtMoney(data.projects, data.sites, data.counts, data.population, names)
    const byWhere = [...dm.rows].sort((a, b) => b.where / b.population - a.where / a.population)
    const top = byWhere.slice(0, 3)
    // The jails have their own plate: here each top district's largest other project, and, counted by whom it serves,
    // the projects that put the top districts ahead.
    const leads = top.map((r) => leadProjectIn(r.district, data.projects, data.sites, (p) => p.id.startsWith('BBJ-'))).filter((s): s is Spot => !!s)
    const jailTop = top.filter((r) => leadProjectIn(r.district, data.projects, data.sites)?.id.startsWith('BBJ-')).length
    const topServes = [...dm.rows].sort((a, b) => b.serves / b.population - a.serves / a.population).slice(0, 3)
    const servingLeads = topServes.map((r) => servingLeadIn(r.district, data.projects, data.sites, data.counts)).filter((s): s is Spot => !!s)
    const psa = megaProject('Penn Station Access', data.projects, data.sites, data.mega)
    const jails = boroughJails(data.projects)
    const jailSpots = jails.jails.map((j) => ({ ...j.spot, note: j.original ? `first recorded at ${money(j.original)}` : undefined }))
    const bld = buildings(data.projects)
    const said = statementsFor('Penn Station Access', data.statements)
    const psaJumps = jumps(psa.series, data.statements.filter((r) => r.mega_project === 'Penn Station Access'))
    const dots = siteDots(data.projects, data.sites)
    const groups = siteGroups(dots)
    // The project plate's stations: the exported walk zones (names from psa_stations), else the project's sites.
    const reach = data.reach.filter((r) => r.mega_project === 'Penn Station Access')
    const stations = reach.length ? reach.map((r) => ({ lon: r.lon, lat: r.lat, place: r.station, residents: r.residents })) : psa.stations
    const terminals = (data.rail?.features ?? []).filter((f) => f.properties?.line === 'terminal' && f.geometry.type === 'Point')
      .map((f) => { const [lon, lat] = (f.geometry as Point).coordinates; return { lon, lat } })
    const placed = new Map(dots.map((d) => [d.id, d.tier]))
    const approx = [...placed.values()].filter((t) => t === 'B').length
    return { names, totals, spots, dm, leads, top, jailTop, topServes, servingLeads, psa, psaJumps, terminals, said, jails, jailSpots, bld, groups, stations, placed: placed.size, approx }
  }, [data])

  const view: View = useMemo(() => {
    if (!computed) return { kind: 'builders', focus: null }
    if (active === 'resident') {
      const vals = computed.dm.rows.map((r) => ({ d: r.district, v: (step === 'where' ? r.where : r.serves) / r.population }))
      return { kind: 'districts', fills: quantileFills(vals), focus }
    }
    if (active === 'jails') return { kind: 'spots', focus }
    if (active === 'psa') return { kind: 'stations', stations: computed.stations, extent: computed.terminals, focus: null }
    return { kind: 'builders', focus }
  }, [computed, active, step, focus])

  const spotsOnMap = useMemo(() => (!computed ? NONE : active === 'builders' ? computed.spots : active === 'jails' ? computed.jailSpots : active === 'resident' ? (step === 'where' ? computed.leads : computed.servingLeads) : NONE), [computed, active, step])
  const padding = useMemo(() => (phone ? { top: 16, right: 16, bottom: 16, left: 16 } : { top: 30, right: 30, bottom: 30, left: 30 }), [phone])
  const cameraKey = `${active}|${focus?.id ?? ''}|${phone ? 'phone' : 'desk'}|${computed ? 'ready' : 'loading'}`

  if (error) return <div className="story-state"><p>The data did not load: {error}</p><a href={TOOL}>Open the map instead</a></div>

  return (
    <div className="story">
      <div className="story-sheet">
        {!phone && <a className="skip skip-desk" href={TOOL}>Skip to the map</a>}
        <StoryMap view={view} groups={computed?.groups ?? []} rail={data?.rail ?? null} districts={data?.districts ?? null} spots={spotsOnMap} padding={padding}
          highlight={active === 'builders' ? highlight : null} hot={hot} onHot={setHot} cameraKey={cameraKey} phone={phone} />
      </div>
      {phone && <PaneGrip />}
      <aside className="story-column" ref={column}>
        <KeySheet active={active} stopped={stopped} boroughs={data?.boroughs ?? null} frame={active === 'psa' && computed ? [...computed.stations, ...computed.terminals] : null} phone={phone} />
        {!computed && <p className="story-loading">Loading the latest reports…</p>}
        {computed && data && (
          <>
            <Plate id="builders" n={n('builders')} title="Three builders">
              <p className="lede">Three public bodies build most of what is going up in New York. Each keeps its own books, so they stand side by side here and are never added together.</p>
              <BuildersTable totals={computed.totals} highlight={highlight} onHighlight={setHighlight} />
              <p>The city has the most money in play. The School Construction Authority runs the most projects, most of them repairs to schools. The MTA's projects are fewer and larger: a new signal system or a fleet of cars is one project.</p>
              <p className="map-key">Each dot is a place with unfinished work, sized by the money there and tinted by the builder with most of it: projects at one address count together, and a project at several sites, such as a signal job along a line, is shared across them. {computed.approx.toLocaleString()} of the {computed.placed.toLocaleString()} projects are placed by the facility their title names rather than by an address, so their spot is approximate.</p>
              <OnTheGround spots={computed.spots} focus={focus} onFocus={setFocus} hot={hot} onHot={setHot} caption="The largest project each body has at one known address" />
              <Sources text={`City: Capital Projects Dashboard, ${periodLabel(data.manifest.latest_snapshot)} report. Schools: SCA capital data. MTA: Capital Dashboard. Unfinished projects only; nominal dollars.`} />
            </Plate>

            <Plate id="jails" n={n('jails')} title="The jails">
              <JailsPlate jails={computed.jails} series={data.series} spots={computed.jailSpots} bld={computed.bld} focus={focus} onFocus={setFocus} hot={hot} onHot={setHot} />
            </Plate>

            <Plate id="resident" n={n('resident')} title="Per resident">
              <p className="lede">Divide the city's capital money by the people who live where it counts, and a few districts stand far apart.</p>
              <div className="steps" role="group" aria-label="Count money">
                <button type="button" aria-pressed={step === 'where'} onClick={() => { setStep('where'); setFocus(null) }}>Where the work is</button>
                <button type="button" aria-pressed={step === 'serves'} onClick={() => { setStep('serves'); setFocus(null) }}>Whom it serves</button>
              </div>
              <p className="step-note">
                {step === 'where'
                  ? 'Each project counts in the district where it is built, wherever its users live.'
                  : 'Each project counts in the area it is built for: a library in its district, a borough jail across its borough, a water tunnel across the whole city (which is left off the map).'}
              </p>
              <RampKey dm={computed.dm} step={step} />
              <Dumbbell dm={computed.dm} />
              {step === 'where'
                ? <>
                  <p>Counted where the work is, {listNames(computed.top.map((r) => r.name))} lead{computed.jailTop ? <>, {computed.jailTop === computed.top.length ? 'each' : `${computed.jailTop} of them`} holding one of the borough-based jails of plate {n('jails')}. A jail serves its whole borough, so counted by whom it serves, its money spreads across the borough and the districts draw closer</> : ''}.</p>
                  <OnTheGround spots={computed.leads} focus={focus} onFocus={setFocus} hot={hot} onHot={setHot} caption="Besides the jails, the largest project in each" />
                </>
                : <>
                  <p>Counted by whom it serves, {listNames(computed.topServes.map((r) => r.name))} lead: work built for the people who live there, at a scale few districts see.</p>
                  <OnTheGround spots={computed.servingLeads} focus={focus} onFocus={setFocus} hot={hot} onHot={setHot} caption="What puts them ahead (estimate)" />
                </>}
              <p className="estimate-note"><span className="est" aria-hidden="true" /> Hatched figures rest on this project's own estimate of the area each project serves, built from the city's Statement of Needs definitions and subway ridership. They are not official data.</p>
              <Sources text="City capital projects; 2020 census population by tract; community district names from City Planning." />
            </Plate>

            <Plate id="psa" n={n('psa')} title="Penn Station Access">
              <ProjectPlate psa={computed.psa} said={computed.said} jumps={computed.psaJumps} stations={computed.stations} />
            </Plate>

            <Plate id="map" n={n('map')} title="The map">
              <p className="lede">Every project in the three programs, with how precisely each is placed, is on the map.</p>
              <a className="to-map" href={TOOL}>Open the map</a>
            </Plate>
          </>
        )}
      </aside>
    </div>
  )
}

function quantileFills(vals: { d: string; v: number }[]): Map<string, string> {
  const sorted = vals.map((x) => x.v).filter((v) => v > 0).sort((a, b) => a - b)
  const cut = (q: number) => sorted[Math.min(sorted.length - 1, Math.floor(q * sorted.length))]
  const breaks = RAMP.slice(1).map((_, i) => cut((i + 1) / RAMP.length))
  return new Map(vals.map(({ d, v }) => [d, v > 0 ? RAMP[breaks.filter((b) => v >= b).length] : '#f3f5f4']))
}

/** A chart's drawn width: its container's, so its text keeps its real size at every width. */
function useWidth(initial = 420): [React.RefObject<HTMLElement | null>, number] {
  const ref = useRef<HTMLElement>(null)
  const [w, setW] = useState(initial)
  useEffect(() => {
    if (!ref.current) return
    const ro = new ResizeObserver(([e]) => setW(Math.max(260, Math.round(e.contentRect.width))))
    ro.observe(ref.current)
    return () => ro.disconnect()
  }, [])
  return [ref, w]
}

function Plate({ id, n, title, children }: { id: PlateId; n: number; title: string; children: React.ReactNode }) {
  return (
    <section className="plate" id={`plate-${id}`} aria-labelledby={`h-${id}`}>
      <h2 id={`h-${id}`} className="plate-title"><span className="plate-no" aria-label={`Plate ${n}`}>{n}</span>{title}</h2>
      {children}
    </section>
  )
}

function KeySheet({ active, stopped, boroughs, frame, phone }: { active: PlateId; stopped: PlateId | null; boroughs: FeatureCollection | null; frame: { lon: number; lat: number }[] | null; phone: boolean }) {
  // The key's height sets how far below it a plate's title lands when a tab is chosen.
  const nav = useRef<HTMLElement>(null)
  useEffect(() => {
    if (!nav.current) return
    const ro = new ResizeObserver(([e]) => document.documentElement.style.setProperty('--key-h', `${Math.ceil(e.borderBoxSize[0].blockSize)}px`))
    ro.observe(nav.current)
    return () => ro.disconnect()
  }, [])
  const go = (id: PlateId) => document.getElementById(`plate-${id}`)?.scrollIntoView({ behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' })
  const n = PLATES.find((p) => p.id === active)?.n ?? 1
  return (
    <nav className="key" aria-label="Plates" ref={nav}>
      {!phone && boroughs && <KeyMap boroughs={boroughs} frame={frame} n={n} />}
      <ol className="tabs">
        {PLATES.map((p) => (
          <li key={p.id}>
            <button type="button" className="tab" aria-current={active === p.id ? 'step' : undefined} onClick={() => go(p.id)}>
              <span className="tab-no">{p.n}</span><span className="tab-name">{p.title}</span>
              {stopped === p.id && active !== p.id && <span className="flag" title="Where you stopped last time">Last read</span>}
            </button>
          </li>
        ))}
      </ol>
      {phone && <a className="skip" href={TOOL}>Skip to the map</a>}
    </nav>
  )
}

const PANE_KEY = 'story-map-pane'
const PANE_MIN = 0.25, PANE_MAX = 0.75

/** On a phone, the line between the map pane and the plates: drag it to give the map more or less of the screen.
 * The height is kept for the next visit. */
function PaneGrip() {
  const set = (frac: number) => document.documentElement.style.setProperty('--map-h', `${(Math.min(PANE_MAX, Math.max(PANE_MIN, frac)) * 100).toFixed(1)}dvh`)
  useEffect(() => {
    try { const f = Number(localStorage.getItem(PANE_KEY)); if (f) set(f) } catch { /* storage blocked: the default height stands */ }
  }, [])
  const down = (e: React.PointerEvent<HTMLDivElement>) => {
    e.currentTarget.setPointerCapture(e.pointerId)
    e.currentTarget.dataset.dragging = 'true'
  }
  const move = (e: React.PointerEvent<HTMLDivElement>) => {
    if (e.currentTarget.dataset.dragging === 'true') set(e.clientY / window.innerHeight)
  }
  const up = (e: React.PointerEvent<HTMLDivElement>) => {
    delete e.currentTarget.dataset.dragging
    const frac = Math.min(PANE_MAX, Math.max(PANE_MIN, e.clientY / window.innerHeight))
    try { localStorage.setItem(PANE_KEY, frac.toFixed(3)) } catch { /* storage blocked */ }
  }
  return (
    <div className="pane-grip" role="separator" aria-orientation="horizontal" aria-label="Drag to resize the map"
      onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerCancel={up}><i /></div>
  )
}

/** The key map: the five boroughs in outline, the current plate's extent drawn as a numbered sheet. */
function KeyMap({ boroughs, frame, n }: { boroughs: FeatureCollection; frame: { lon: number; lat: number }[] | null; n: number }) {
  const W = 220, H = 200, [x0, x1, y0, y1] = [-74.26, -73.69, 40.49, 40.92]
  const k = Math.cos((40.7 * Math.PI) / 180)
  const sx = W / ((x1 - x0) * k), sy = H / (y1 - y0), s = Math.min(sx, sy)
  const px = (lon: number) => (lon - x0) * k * s, py = (lat: number) => H - (lat - y0) * s
  const path = (g: Geometry) => {
    const polys = g.type === 'MultiPolygon' ? g.coordinates : g.type === 'Polygon' ? [g.coordinates] : []
    return polys.map((poly) => poly.map((ring) => ring.filter((_, i) => i % 6 === 0).map((c, i) => `${i ? 'L' : 'M'}${px(c[0]).toFixed(1)},${py(c[1]).toFixed(1)}`).join('') + 'Z').join('')).join('')
  }
  // eslint-disable-next-line react-hooks/exhaustive-deps -- the projection is fixed; only the outlines change
  const d = useMemo(() => boroughs.features.map((f) => path(f.geometry)).join(''), [boroughs])
  const box = frame && frame.length
    ? (() => { const xs = frame.map((f) => px(f.lon)), ys = frame.map((f) => py(f.lat)); return { x: Math.min(...xs) - 8, y: Math.min(...ys) - 8, w: Math.max(...xs) - Math.min(...xs) + 16, h: Math.max(...ys) - Math.min(...ys) + 16 } })()
    : { x: 4, y: 4, w: W - 8, h: H - 8 }
  return (
    <svg className="keymap" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Key map: plate ${n} covers ${frame ? 'Midtown Manhattan to the East Bronx' : 'the whole city'}`}>
      <path d={d} className="keymap-land" />
      <rect x={box.x} y={box.y} width={box.w} height={box.h} className={`keymap-frame${frame ? ' part' : ''}`} />
      <rect x={box.x} y={box.y} width={22} height={18} className="keymap-no-box" />
      <text x={box.x + 11} y={box.y + 13.5} className="keymap-no">{n}</text>
    </svg>
  )
}

function BuildersTable({ totals, highlight, onHighlight }: { totals: ReturnType<typeof programTotals>; highlight: string | null; onHighlight: (id: string | null) => void }) {
  const maxN = Math.max(...totals.map((t) => t.projects)), maxB = Math.max(...totals.map((t) => t.budget))
  return (
    <table className="ledger">
      <caption className="visually-hidden">Unfinished projects and money by program</caption>
      <thead><tr><th scope="col">Builder</th><th scope="col">Projects</th><th scope="col">Money</th></tr></thead>
      <tbody>
        {totals.map((t) => (
          <tr key={t.id} className={highlight === t.id ? 'lit' : highlight ? 'unlit' : undefined}
            onMouseEnter={() => onHighlight(t.id)} onMouseLeave={() => onHighlight(null)}>
            <th scope="row"><i className="swatch" style={{ background: tintOf(t.id) }} /><span className="long">{t.label}</span><span className="short">{PROGRAMS.find((p) => p.id === t.id)?.short}</span></th>
            <td><span className="bar" style={{ width: `${(100 * t.projects) / maxN}%`, background: tintOf(t.id) }} /><span className="num">{t.projects.toLocaleString()}</span></td>
            <td><span className="bar" style={{ width: `${(100 * t.budget) / maxB}%`, background: tintOf(t.id) }} /><span className="num">{money(t.budget)}</span></td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function RampKey({ dm, step }: { dm: ReturnType<typeof districtMoney>; step: 'where' | 'serves' }) {
  const vals = dm.rows.map((r) => (step === 'where' ? r.where : r.serves) / r.population).filter((v) => v > 0).sort((a, b) => a - b)
  return (
    <div className="ramp" aria-label="Map key: money per resident">
      <span className="ramp-end">{perResident(vals[0] ?? 0)}</span>
      <span className="ramp-bar">{RAMP.map((c) => <i key={c} style={{ background: c }} />)}</span>
      <span className="ramp-end">{perResident(vals.at(-1) ?? 0)}{step === 'serves' && <span className="est" title="Estimate" />}</span>
      <span className="ramp-label">per resident, by community district{step === 'serves' ? `; plus ${perResident(dm.citywidePerResident)} each for citywide work` : ''}</span>
    </div>
  )
}

/** The districts that move most between the two counts: an arrow from where the work is (solid dot) to whom it
 * serves (hatched dot, an estimate). */
function Dumbbell({ dm }: { dm: ReturnType<typeof districtMoney> }) {
  const rows = [...dm.rows].map((r) => ({ ...r, a: r.where / r.population, b: r.serves / r.population }))
    .sort((x, y) => Math.abs(y.a - y.b) - Math.abs(x.a - x.b)).slice(0, 10).sort((x, y) => y.a - x.a)
  const max = Math.max(...rows.flatMap((r) => [r.a, r.b]))
  const [ref, W] = useWidth()
  // Narrow: each district's name sits above its row; wide: in a column on the left.
  const stacked = W < 480
  const L = stacked ? 8 : Math.min(210, W * 0.42), R = 14, rowH = stacked ? 44 : 28, rDot = 6, top = stacked ? 46 : 32
  const ticks = niceTicks(max, stacked ? 3 : 4)
  const x = (v: number) => L + (v / ticks.at(-1)!) * (W - L - R)
  return (
    <figure className="dumbbell" ref={ref as React.RefObject<HTMLElement>}>
      <figcaption>The ten districts that change most between the two counts, money per resident</figcaption>
      <svg viewBox={`0 0 ${W} ${rows.length * rowH + top - rowH / 2 + 8}`} width={W} role="img" aria-label="Money per resident, counted where the work is and by whom it serves">
        <defs>
          <pattern id="hatch" width="4" height="4" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="4" height="4" fill="#ffffff" /><rect width="2" height="4" fill="#2a78d6" /></pattern>
          <marker id="db-arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0.5L8,4L0,7.5Z" className="db-head" /></marker>
        </defs>
        {ticks.map((t, i) => (
          <g key={t}>
            <line x1={x(t)} x2={x(t)} y1={16} y2={rows.length * rowH + top - rowH / 2} className="db-grid" />
            <text x={x(t)} y={11} className="db-axis" textAnchor={i === 0 ? 'start' : i === ticks.length - 1 ? 'end' : 'middle'}>{perResident(t)}</text>
          </g>
        ))}
        {rows.map((r, i) => {
          const y = i * rowH + top
          const dir = Math.sign(r.b - r.a), end = x(r.b) - dir * (rDot + 1.5)
          return (
            <g key={r.district}>
              <title>{`${r.name}: ${perResident(r.a)} where the work is, ${perResident(r.b)} by whom it serves (estimate)`}</title>
              {stacked
                ? <text x={L} y={y - 12} className="db-name" textAnchor="start">{r.name}</text>
                : <text x={L - 10} y={y + 4} className="db-name" textAnchor="end">{r.name.length > 34 ? r.name.slice(0, 33) + '…' : r.name}</text>}
              {Math.abs(end - x(r.a)) > 6 && <line x1={x(r.a)} x2={end} y1={y} y2={y} className="db-link" markerEnd="url(#db-arrow)" />}
              <circle cx={x(r.a)} cy={y} r={4} className="db-where" />
              <circle cx={x(r.b)} cy={y} r={rDot} fill="url(#hatch)" className="db-serves" />
            </g>
          )
        })}
      </svg>
      <div className="db-key"><span><i className="k-where" />where the work is</span><span aria-hidden="true">→</span><span><i className="k-serves" />whom it serves (estimate)</span></div>
    </figure>
  )
}

/** Published commentary and analysis a plate cites: who, what, when, what kind, and whether it was read in full. */
interface Cite { publisher: string; title: string; date: string; url: string; kind: 'official' | 'research' | 'press' }
const JAIL_CITES: Cite[] = [
  { publisher: 'City Planning Commission', title: 'Report on C 200143 MMY, Rikers Island public place mapping (pp. 2, 6)', date: 'October 21, 2020', url: 'https://www.nyc.gov/assets/planning/download/pdf/about/cpc/200143.pdf', kind: 'official' },
  { publisher: 'NYC Department of Design and Construction', title: 'New Brooklyn Jail Reaches the Top, in Latest Step Toward Closing Rikers Island', date: 'April 23, 2026', url: 'https://www.nyc.gov/site/ddc/about/press-releases/2026/pr-042326-Brooklyn-BBJ-Facility.page', kind: 'official' },
  { publisher: 'Queens Daily Eagle', title: 'Borough-based jail costs double to $16 billion, mayor claims', date: 'April 25, 2024', url: 'https://queenseagle.com/all/2024/4/25/borough-based-jail-costs-double-to-16-billion-mayor-claims', kind: 'press' },
  { publisher: 'New York City Comptroller', title: 'Cost of Incarceration per Person in New York City Skyrockets to All-Time High', date: 'December 6, 2021', url: 'https://comptroller.nyc.gov/newsroom/comptroller-stringer-cost-of-incarceration-per-person-in-new-york-city-skyrockets-to-all-time-high-2', kind: 'official' },
  { publisher: 'CUNY Institute for State and Local Governance', title: 'Closing Rikers Cannot Wait', date: 'October 12, 2021', url: 'https://islg.cuny.edu/blog/closing-rikers-cannot-wait', kind: 'research' },
]

function JailsPlate({ jails, series, spots, bld, focus, onFocus, hot, onHot }: { jails: ReturnType<typeof boroughJails>; series: SeriesRow[]; spots: Spot[]; bld: ReturnType<typeof buildings>; focus: Spot | null; onFocus: (s: Spot | null) => void; hot: string | null; onHot: (id: string | null) => void }) {
  const when = jails.originalPeriod ? `${MONTHS[(jails.originalPeriod % 100) - 1]} ${Math.floor(jails.originalPeriod / 100)}` : 'first recorded'
  const places = bld.places.reduce((t, p) => t + p.budget, 0)
  return (
    <>
      <p className="lede">The city is building {["no", "one", "two", "three", "four", "five", "six"][jails.projects] ?? jails.projects} jails, in Brooklyn, Queens, the Bronx and Manhattan, to replace the jails on Rikers Island, where a City Map change approved by the City Planning Commission in 2020 bars holding anyone after August 31, 2027. None will be ready by then: the city's builder expects Brooklyn's in spring 2029, the Bronx's and Queens's in 2031 and Manhattan's in 2032.</p>
      <OnTheGround spots={spots} focus={focus} onFocus={onFocus} hot={hot} onHot={onHot} caption="The four jails" />
      <table className="work">
        <caption>Each jail's record</caption>
        <thead><tr><th scope="col">Jail</th><th scope="col">{when}</th><th scope="col">Now</th><th scope="col">Spent</th></tr></thead>
        <tbody>
          {jails.jails.map((j) => (
            <tr key={j.spot.id}><th scope="row">{j.borough}<br /><span className="cell-note">{j.spot.place}</span></th><td className="num">{j.original ? money(j.original) : '—'}</td><td className="num">{money(j.budget)}</td><td className="num">{money(j.spent)}</td></tr>
          ))}
          <tr className="rest"><th scope="row">All four</th><td className="num">{money(jails.original)}</td><td className="num">{money(jails.budget)}</td><td className="num">{money(jails.jails.reduce((t, j) => t + j.spent, 0))}</td></tr>
        </tbody>
      </table>
      {series.length > 0 && <JailCosts jails={jails} series={series} />}
      <BuildingsChart bld={bld} original={jails.original} when={when} />
      <p>The four jails hold {money(jails.budget)}, against {money(jails.original)} when first recorded in {when}: most of the {money(bld.corrections)} the city has in jails and corrections, more than its libraries, cultural institutions, police, fire and EMS, shelters and older adults' centers together ({money(places)}), and more than every park ({money(bld.parks)}).</p>
      <p>Each record is scheduled in stages: one clears what stands on the site (the city's reports spell it "Dismantal"), the other builds the new jail; Queens's also lays a water main.</p>
      <p>Building them is one cost. Published analysis adds two more: running a jail cost $556,539 per person in fiscal 2021, counting fringe benefits and health care (the City Comptroller), and a smaller system running at its target of 3,300 people could save nearly $2 billion a year (CUNY's Institute for State and Local Governance).</p>
      <p>The 2027 date is a note on the City Map. The Department of Correction, the Mayor's Office of Criminal Justice and the Council Speaker applied for it in 2019 with the end of 2026, and in October 2020, days before the City Planning Commission approved it, moved the date to August 31, 2027, citing delays in procurement and design during the pandemic. The city's Capital Projects Dashboard gives no finish date for any of the four new jails; the dates above are the Department of Design and Construction's, from April 2026.</p>
      <Cites cites={JAIL_CITES} />
      <Sources text="City capital projects: each jail's design-build record (BBJ-K, -M, -Q, -X), its first budget recorded (Open Data qj5n-h5qp) and spending to date; stage names and the absence of finish dates from the Capital Projects Dashboard. Completion dates: NYC Department of Design and Construction. Nominal dollars." />
    </>
  )
}

/** A tint per borough for the jails chart (from the site's validated categorical hues). */
const BOROUGH_TINT: Record<string, string> = { Queens: '#2a78d6', Manhattan: '#eb6834', Bronx: '#1baf7a', Brooklyn: '#4a3aa7' }

/** Each jail's budget report by report on one chart, a line per jail tinted by borough and named at its end: OMB's
 * planned totals (2020-2023), then the dashboard's budget; a ring marks the budget first recorded. */
function JailCosts({ jails, series }: { jails: ReturnType<typeof boroughJails>; series: SeriesRow[] }) {
  const [ref, W] = useWidth()
  const H = 230, L = 46, R = 118, T = 10, B = 22
  const periods = [...new Set(series.map((r) => r.period))].sort((a, b) => a - b)
  const t = (p: number) => Math.floor(p / 100) + ((p % 100) - 1) / 12
  const [t0, t1] = [t(periods[0]), t(periods.at(-1)!)]
  const ticks = niceTicks(Math.max(...series.map((r) => r.budget)), 3)
  const x = (p: number) => L + ((t(p) - t0) / (t1 - t0)) * (W - L - R)
  const y = (v: number) => T + (1 - v / ticks.at(-1)!) * (H - T - B)
  const label = (p: number) => `${MONTHS[(p % 100) - 1].slice(0, 3)} ${Math.floor(p / 100)}`
  const lines = jails.jails.map((j) => {
    const rows = series.filter((r) => r.id === j.spot.id)
    const step = rows.slice(1).map((r, i) => ({ p: r.period, d: r.budget - rows[i].budget })).sort((a, b) => b.d - a.d)[0]
    const d = rows.map((r, i) => `${i ? `H${x(r.period).toFixed(1)}V` : `M${x(r.period).toFixed(1)},`}${y(r.budget).toFixed(1)}`).join('')
    return { j, rows, step, d, tint: BOROUGH_TINT[j.borough ?? ''] ?? '#7b8494', end: y(rows.at(-1)?.budget ?? 0) }
  }).filter((l) => l.rows.length > 1).sort((a, b) => a.end - b.end)
  // End labels at least 15 px apart, pushed down in order from the top.
  lines.forEach((l, i) => { l.end = Math.max(l.end, i ? lines[i - 1].end + 15 : l.end) })
  const steps = lines.filter((l) => l.step && l.step.d > 1e8).sort((a, b) => a.step!.p - b.step!.p)
  return (
    <figure className="jail-costs" ref={ref as React.RefObject<HTMLElement>}>
      <figcaption>Each jail's budget, report by report, {label(periods[0])} to {label(periods.at(-1)!)}</figcaption>
      <svg viewBox={`0 0 ${W} ${H}`} width={W} role="img" aria-label={lines.map((l) => `${l.j.borough}: ${money(l.rows[0].budget)} to ${money(l.rows.at(-1)!.budget)}`).join('; ')}>
        {ticks.map((v) => (
          <g key={v}>
            <line x1={L} x2={W - R} y1={y(v)} y2={y(v)} className={v ? 'db-grid' : 'axis'} />
            <text x={L - 6} y={y(v) + 4} className="tick" textAnchor="end">{v ? money(v) : '$0'}</text>
          </g>
        ))}
        {lines.map((l) => (
          <g key={l.j.spot.id}>
            <path d={l.d} className="jc-line" style={{ stroke: l.tint }}><title>{l.rows.map((r) => `${label(r.period)}: ${money(r.budget)}`).join('\n')}</title></path>
            {l.j.original && jails.originalPeriod && <circle cx={x(jails.originalPeriod)} cy={y(l.j.original)} r={3.5} className="jc-first" style={{ stroke: l.tint }}><title>{`${l.j.borough}, first recorded ${label(jails.originalPeriod)}: ${money(l.j.original)}`}</title></circle>}
            <text x={W - R + 8} y={l.end + 4} className="jc-name" style={{ fill: l.tint }}>{l.j.borough} <tspan className="jc-v">{money(l.rows.at(-1)!.budget)}</tspan></text>
          </g>
        ))}
        <text x={L} y={H - 4} className="tick">{Math.floor(periods[0] / 100)}</text>
        <text x={W - R} y={H - 4} className="tick" textAnchor="end">{Math.floor(periods.at(-1)! / 100)}</text>
      </svg>
      {steps.length > 0 && <p className="bars-key">Each rose in one step: {steps.map((l) => `${l.j.borough} +${money(l.step!.d)} (${label(l.step!.p)} report)`).join(', ')}.</p>}
      <p className="bars-key">The line: to early 2023, OMB's planned total for each record (Capital Project Detail Data); from May 2023, the Capital Projects Dashboard's budget (in May 2023, the one month both report, they agree). <i className="k-first" />the budget first recorded{jails.originalPeriod ? `, ${label(jails.originalPeriod)}` : ''}, as in the table: a separate figure, a little above OMB's planned total then.</p>
    </figure>
  )
}

/** Three bars on one scale: jails and corrections (the borough-based jails within it, their first recorded budget
 * marked), the places people use stacked, and parks. */
function BuildingsChart({ bld, original, when }: { bld: ReturnType<typeof buildings>; original: number; when: string }) {
  const [ref, W] = useWidth()
  const L = 0, R = 64, barH = 20, gap = 52
  const max = Math.max(bld.corrections, bld.places.reduce((t, p) => t + p.budget, 0), bld.parks)
  const x = (v: number) => L + (v / max) * (W - L - R)
  const starts = bld.places.map((_, i) => bld.places.slice(0, i).reduce((t, p) => t + p.budget, 0))
  const acc = bld.places.reduce((t, p) => t + p.budget, 0)
  const stack = bld.places.map((p, i) => ({ ...p, x0: x(starts[i]), x1: x(starts[i] + p.budget), i }))
  const rows = [
    { label: 'Jails and corrections', total: bld.corrections },
    { label: 'Libraries, culture, police, fire, shelters, seniors', total: acc },
    { label: 'Parks', total: bld.parks },
  ]
  return (
    <figure className="bars" ref={ref as React.RefObject<HTMLElement>}>
      <figcaption>Unfinished city capital money</figcaption>
      <svg viewBox={`0 0 ${W} ${rows.length * gap + 6}`} width={W} role="img" aria-label={rows.map((r) => `${r.label}: ${money(r.total)}`).join('; ')}>
        {rows.map((r, i) => <text key={r.label} x={0} y={i * gap + 13} className="bars-label">{r.label}</text>)}
        <rect x={x(0)} y={18} width={x(bld.boroughJails) - x(0)} height={barH} className="bar-jails"><title>{`Borough-based jails: ${money(bld.boroughJails)}`}</title></rect>
        <rect x={x(bld.boroughJails) + 2} y={18} width={Math.max(0, x(bld.corrections) - x(bld.boroughJails) - 2)} height={barH} className="bar-corr"><title>{`Other jails and corrections: ${money(bld.corrections - bld.boroughJails)}`}</title></rect>
        <line x1={x(original)} x2={x(original)} y1={14} y2={18 + barH + 4} className="bar-mark" />
        <text x={x(original) + 4} y={18 + barH + 12} className="bars-note">{when}: {money(original)}</text>
        {stack.map((p) => <rect key={p.label} x={p.x0 + (p.i ? 2 : 0)} y={gap + 18} width={Math.max(0, p.x1 - p.x0 - (p.i ? 2 : 0))} height={barH} className={p.i % 2 ? 'bar-place alt' : 'bar-place'}><title>{`${p.label}: ${money(p.budget)}`}</title></rect>)}
        <rect x={x(0)} y={2 * gap + 18} width={x(bld.parks) - x(0)} height={barH} className="bar-place"><title>{`Parks: ${money(bld.parks)}`}</title></rect>
        {rows.map((r, i) => <text key={r.label} x={x(r.total) + 6} y={i * gap + 18 + barH - 4} className="bars-v">{money(r.total)}</text>)}
      </svg>
      <p className="bars-key"><i className="k-jails" />borough-based jails · <i className="k-corr" />other jails and corrections · {bld.places.map((p) => `${p.label} ${money(p.budget)}`).join(' · ')}</p>
    </figure>
  )
}

function Cites({ cites }: { cites: Cite[] }) {
  return (
    <ul className="cites">
      {cites.map((c) => <li key={c.url}><span className="cite-kind">{c.kind}</span> {c.publisher}, <a href={c.url}>{c.title}</a>, {c.date}</li>)}
    </ul>
  )
}

function OnTheGround({ spots, focus, onFocus, hot, onHot, caption }: { spots: Spot[]; focus: Spot | null; onFocus: (s: Spot | null) => void; hot: string | null; onHot: (id: string | null) => void; caption: string }) {
  return (
    <div className="ground">
      <h3>{caption}</h3>
      <ol>
        {spots.map((s, i) => (
          <li key={s.id}>
            <button type="button" aria-pressed={focus?.id === s.id} className={hot === s.id ? 'hot' : undefined} onClick={() => onFocus(focus?.id === s.id ? null : s)}
              onMouseEnter={() => onHot(s.id)} onMouseLeave={() => onHot(null)} onFocus={() => onHot(s.id)} onBlur={() => onHot(null)}>
              <span className="ground-no">{i + 1}</span>
              <span className="ground-body"><span className="ground-title">{s.title}</span>
                <span className="ground-meta"><i className="swatch" style={{ background: tintOf(s.program) }} />{PROGRAMS.find((p) => p.id === s.program)?.short} · {money(s.budget)}{s.place ? ` · ${s.place}` : ''}{s.note ? ` · ${s.note}` : ''}</span></span>
            </button>
          </li>
        ))}
      </ol>
    </div>
  )
}

function ProjectPlate({ psa, said, jumps, stations }: { psa: ReturnType<typeof megaProject>; said: Map<string, Statement>; jumps: Jump[]; stations: { place: string | null; residents?: number }[] }) {
  const first = psa.series[0], last = psa.series.at(-1)
  const lead = psa.work[0]
  const done = said.get('substantial_completion'), temp = said.get('temporary_service')
  const out1 = said.get('outages_first_year'), out2 = said.get('outages_second_year')
  const doc = done ?? temp
  const pages = [...new Set([...said.values()].flatMap((r) => [...r.quote.matchAll(/(?:^| \| )p(\d+):/g)].map((m) => Number(m[1]))))].sort((a, b) => a - b)
  return (
    <>
      <p className="lede">{stations.length} new Metro-North stations in the East Bronx, on the Amtrak line that carries trains past them today.</p>
      <p>New Haven Line trains end at Grand Central today. Penn Station Access gives the line's riders "direct access to Penn Station" (MTA), on trains over the Hell Gate Line that stop at the new stations.</p>
      {stations.some((s) => s.residents !== undefined) && <WalkZones stations={stations} />}
      {first && last && <Series series={psa.series} jumps={jumps} cause={said.get('budget_change_cause') ?? null} />}
      <p>MTA's money for the project{first && last ? ` went from ${money(first.total)} in ${month(first.load)} to ${money(last.total)} in ${month(last.load)}` : ''}, across {psa.lines.length} budget lines.{lead ? ` The largest, a ${money(lead.budget)} design-build contract, rebuilds the Amtrak line the trains will run on${said.has('budget_majority') ? ", and MTA says most of the project's money goes to that rebuilding" : ''}.` : ''}</p>
      <WorkLedger work={psa.work} completed={psa.completed} />
      {lead && last && (
        <p>
          The {month(last.load)} dashboard {done ? 'still dates' : 'dates'} the {shortLine(lead.title).toLowerCase()} {lead.finish ? month(lead.finish) : 'undated'}{lead.pctComplete !== null ? `, ${lead.pctComplete}% complete` : ''}.
          {done && ` In ${month(done.statement_date)} MTA told the ${done.setting} that substantial completion had moved to ${quarterLabel(done.value)}${temp ? `, with temporary service possible from ${temp.value}` : ''}${out1 && out2 ? `, and laid the delay on Amtrak: ${out1.value} promised weekend track outages in the first year, ${out2.value} in the second` : ''}.`}
        </p>
      )}
      <p className="sources">
        MTA Capital Dashboard (every quarterly load since March 2020)
        {doc && <>; MTA, <a href={doc.url}>presentation to the {doc.setting}, {month(doc.statement_date)}</a> ({pages.length > 1 ? 'pp.' : 'p.'} {pages.join(', ')})</>}
        ; station sites from the project's Environmental Assessment (May 2021); route from MTA's rail branches, the city's railroad layer and, north of the city line, the federal rail network (USDOT); residents within 800 m from the 2020 census, an estimate. Nominal dollars.
      </p>
    </>
  )
}

/** The map key for the walk zones, and each station's count: residents within 800 m (about a ten-minute walk). */
function WalkZones({ stations }: { stations: { place: string | null; residents?: number }[] }) {
  return (
    <div className="walk">
      <div className="ramp" aria-label="Map key: residents within 800 m">
        <span className="ramp-end">0</span>
        <span className="ramp-bar">{PEOPLE.map(([v, c]) => <i key={v} style={{ background: c }} />)}</span>
        <span className="ramp-end">45,000+<span className="est" title="Estimate" /></span>
        <span className="ramp-label">residents within 800 m of each station, about a ten-minute walk, in steps of 15,000</span>
      </div>
      <p className="walk-list">{stations.map((s) => `${s.place}: ${(s.residents ?? 0).toLocaleString()}`).join(' · ')}</p>
    </div>
  )
}

const shortLine = (t: string) => t.replace(/^(Penn Station Access|Psa)\s*:?\s*/i, '').replace(/ For Penn Station Access$/i, '')

/** The project's budget lines as bars, largest first: each bar's length is its money, its filled part the share MTA
 * reports complete, with the dashboard's finish beside it. Lines under $10M are summed in one row. */
function WorkLedger({ work, completed }: { work: ReturnType<typeof megaProject>['work']; completed: ReturnType<typeof megaProject>['completed'] }) {
  const shown = work.filter((w) => w.budget >= 10e6), rest = work.filter((w) => w.budget < 10e6)
  const max = Math.max(...work.map((w) => w.budget))
  const due = (f: string | null) => (f ? (f.length > 4 ? `${MONTHS[Number(f.slice(5, 7)) - 1].slice(0, 3)} ${f.slice(0, 4)}` : f) : 'no date')
  return (
    <figure className="work-bars">
      <figcaption>The work, line by line: length is money, the filled part the share MTA reports complete</figcaption>
      <ol>
        {shown.map((w) => (
          <li key={w.id}>
            <span className="wb-name">{shortLine(w.title)}</span>
            <span className="wb-bar" style={{ width: `${(100 * w.budget) / max}%` }} title={`${money(w.budget)}, ${w.pctComplete === null ? 'share complete not published' : `${w.pctComplete}% complete`}, due ${due(w.finish)}`}>
              <i style={{ width: `${w.pctComplete ?? 0}%` }} />
            </span>
            <span className="wb-meta">{money(w.budget)} · {w.pctComplete === null ? '—' : `${w.pctComplete}%`} done · due {due(w.finish)}</span>
          </li>
        ))}
      </ol>
      <p className="bars-key">{rest.length > 0 && `${rest.length} smaller lines, ${money(rest.reduce((t, w) => t + w.budget, 0))} together. `}{completed.lines > 0 && `${completed.lines} ${completed.lines === 1 ? 'line' : 'lines'} MTA lists as complete, ${money(completed.budget)}.`}</p>
    </figure>
  )
}

/** What MTA says each budget change was for, in a few words (the full sentence is quoted on the page cited). */
const CHANGE_LABEL: Record<string, string> = {
  budget_change_offset: 'moved to other work, made up in the next plan',
  budget_change_letter_amendment: 'added by letter amendment when the design-build contract was awarded',
  budget_change_deferred_costs: 'costs put off in 2021: contingencies, support costs and the New Rochelle Yard option',
  budget_change_rolling_stock_start: 'a first sum toward the trains for the service',
  budget_change_rolling_stock: 'more toward the trains for the service',
}
const quoted = (q: string) => q.split(' | ').map((f) => f.replace(/^p\d+:\s*/, '')).join(' … ')
const pageOf = (q: string) => /^p(\d+):/.exec(q)?.[1]

function Series({ series, jumps, cause }: { series: { load: string; total: number }[]; jumps: Jump[]; cause: Statement | null }) {
  const [ref, W] = useWidth(360)
  const H = 180, L = 52, B = 24, T = 16
  const xs = series.map((_, i) => L + (i / Math.max(1, series.length - 1)) * (W - L - 10))
  const max = Math.max(...series.map((s) => s.total))
  const y = (v: number) => T + (1 - v / max) * (H - T - B)
  const d = series.map((s, i) => `${i ? 'L' : 'M'}${xs[i].toFixed(1)},${y(s.total).toFixed(1)}`).join('')
  const last = series.length - 1
  // Steps under $50M are not marked on the line; a note under the list gives them in a few words.
  const big = jumps.filter((j) => Math.abs(j.change) >= 50e6), minor = jumps.filter((j) => Math.abs(j.change) < 50e6)
  const marks = big.map((j, n) => ({ ...j, n: n + 1, i: series.findIndex((s) => s.load === j.load) })).filter((j) => j.i > 0)
  return (
    <figure className="series" ref={ref as React.RefObject<HTMLElement>}>
      <figcaption>MTA money for Penn Station Access, each quarterly report</figcaption>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Money for Penn Station Access by quarterly report">
        <line x1={L} x2={W - 10} y1={y(0)} y2={y(0)} className="axis" />
        <text x={L - 6} y={y(max) + 4} className="tick" textAnchor="end">{money(max)}</text>
        <text x={L - 6} y={y(0) + 4} className="tick" textAnchor="end">$0</text>
        <path d={`${d}L${xs[last]},${y(0)}L${xs[0]},${y(0)}Z`} className="series-area" />
        <path d={d} className="series-line" />
        {series.map((s, i) => <circle key={s.load} cx={xs[i]} cy={y(s.total)} r={3} className="series-dot"><title>{`${s.load.slice(0, 7)}: ${money(s.total)}`}</title></circle>)}
        {marks.map((j) => (
          <g key={j.load} className="jump-mark" transform={`translate(${xs[j.i] - 13},${y(series[j.i].total) - 2})`}>
            <circle r={8} /><text y={3.5} textAnchor="middle">{j.n}</text>
          </g>
        ))}
        <text x={xs[0]} y={H - 6} className="tick">{series[0].load.slice(0, 4)}</text>
        <text x={xs[last]} y={H - 6} className="tick" textAnchor="end">{series[last].load.slice(0, 4)}</text>
      </svg>
      {marks.length > 0 && (
        <ol className="jumps">
          {marks.map((j) => (
            <li key={j.load}>
              <span className="jump-no">{j.n}</span>
              <span><b>{month(j.load)}, {j.change > 0 ? '+' : '−'}{money(Math.abs(j.change))}</b>{j.said.length ? `: ${j.said.map((r) => CHANGE_LABEL[r.kind] ?? r.kind.replace('budget_change_', '').replaceAll('_', ' ')).join('; and ')}` : ''}{j.said.length ? <> (<a href={`${j.said[0].url}#page=${pageOf(j.said[0].quote)}`}>MTA, p. {pageOf(j.said[0].quote)}</a>)</> : ''}.</span>
            </li>
          ))}
        </ol>
      )}
      {minor.length > 0 && <p className="jump-cause">Also {listNames(minor.map((j) => `${j.change > 0 ? '+' : '−'}${money(Math.abs(j.change))} in ${month(j.load)}${j.said.length ? ` (${j.said.map((r) => CHANGE_LABEL[r.kind] ?? r.kind).join('; ')})` : ''}`))}.</p>}
      {cause && <p className="jump-cause">MTA on {listNames(marks.filter((j) => j.said.some((r) => r.document === cause.document)).map((j) => String(j.n))).replace(/^(\d+)$/, 'change $1').replace(/^(\d.*and.*)$/, 'changes $1')}: <q>{quoted(cause.quote)}</q> (<a href={`${cause.url}#page=${pageOf(cause.quote)}`}>{cause.setting}, p. {pageOf(cause.quote)}</a>)</p>}
    </figure>
  )
}

function Sources({ text }: { text: string }) {
  return <p className="sources">{text}</p>
}

/** Round axis steps from 0 to at least `max`: n or so steps of 1, 2 or 5 times a power of ten. */
function niceTicks(max: number, n: number): number[] {
  const raw = max / n, p = 10 ** Math.floor(Math.log10(raw)), step = [1, 2, 5, 10].map((m) => m * p).find((s) => s >= raw)!
  return Array.from({ length: Math.ceil(max / step) + 1 }, (_, i) => i * step)
}

function listNames(names: string[]): string {
  return names.length < 2 ? names.join('') : `${names.slice(0, -1).join(', ')} and ${names.at(-1)}`
}

function month(ym: string): string {
  return `${MONTHS[Number(ym.slice(5, 7)) - 1]} ${ym.slice(0, 4)}`
}

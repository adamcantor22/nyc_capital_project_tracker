import type { FeatureCollection, Geometry } from 'geojson'
import { useEffect, useMemo, useState } from 'react'
import type { Site } from '../areas/aggregate'
import { fetchJson, loadAll, loadSites } from '../data/load'
import type { Manifest, Project } from '../data/types'
import { MONTHS, periodLabel } from '../ui/format'
import {
  boroughJails, buildings, districtMoney, largestPlaced, leadProjectIn, megaProject, money, perResident, PROGRAMS, programTotals, tintOf,
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
const TOOL = import.meta.env.BASE_URL

interface Data {
  manifest: Manifest
  projects: Project[]
  sites: Map<string, Site[]>
  districts: FeatureCollection
  boroughs: FeatureCollection
  counts: Record<string, AreaCount[]>
  population: PopulationRow[]
  mega: MegaPoint[]
  statements: Statement[]
  rail: FeatureCollection | null
  reach: StationReach[]
}

/** One row of station_reach.json (pipeline/rail.py): residents within 800 m of a new station, an estimate. */
interface StationReach { mega_project: string; no: number; station: string; lon: number; lat: number; radius_m: number; residents: number }

async function load(): Promise<Data> {
  const { manifest, projects } = await loadAll()
  const [sites, districts, boroughs, counts, population, mega, statements, rail, reach] = await Promise.all([
    loadSites(manifest),
    fetchJson<FeatureCollection>('areas/districts.geojson'),
    fetchJson<FeatureCollection>('areas/boroughs.geojson'),
    fetchJson<Record<string, AreaCount[]>>('area_counts.json'),
    fetchJson<PopulationRow[]>('area_population.json'),
    fetchJson<MegaPoint[]>('mta_mega_series.json'),
    // Absent from data releases before it was exported: the plate then leaves MTA's statements out.
    fetchJson<Statement[]>('mta_mega_statements.json').catch(() => [] as Statement[]),
    fetchJson<FeatureCollection>('rail_lines.geojson').catch(() => null),
    fetchJson<StationReach[]>('station_reach.json').catch(() => [] as StationReach[]),
  ])
  return { manifest, projects, sites, districts, boroughs, counts, population, mega, statements, rail, reach }
}

const readResume = (): PlateId | null => {
  try { return (localStorage.getItem(RESUME_KEY) as PlateId | null) } catch { return null }
}
const writeResume = (id: PlateId) => {
  try { localStorage.setItem(RESUME_KEY, id) } catch { /* storage blocked: resume is a convenience */ }
}

function usePhone() {
  const q = '(max-width: 760px)'
  const [phone, setPhone] = useState(() => window.matchMedia(q).matches)
  useEffect(() => {
    const m = window.matchMedia(q)
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
  const [hot, setHot] = useState<string | null>(null)
  const [highlight, setHighlight] = useState<string | null>(null)
  const phone = usePhone()

  useEffect(() => { load().then(setData, (e: Error) => setError(e.message)) }, [])
  useEffect(() => { if (active !== 'builders') writeResume(active) }, [active])
  const focus = focused && focused.plate === active ? focused.spot : null
  const setFocus = (s: Spot | null) => setFocused(s ? { plate: active, spot: s } : null)

  // A link to a plate (#plate-resident) opens on it once the plates exist.
  useEffect(() => {
    if (data && location.hash.startsWith('#plate-')) document.getElementById(location.hash.slice(1))?.scrollIntoView()
  }, [data])

  // The plate whose top has crossed the middle of the viewport is the one being read.
  useEffect(() => {
    if (!data) return
    const els = PLATES.map((p) => document.getElementById(`plate-${p.id}`)).filter((e): e is HTMLElement => !!e)
    const io = new IntersectionObserver((entries) => {
      for (const e of entries) if (e.isIntersecting) setActive(e.target.id.replace('plate-', '') as PlateId)
    }, { rootMargin: '-45% 0px -50% 0px' })
    els.forEach((e) => io.observe(e))
    return () => io.disconnect()
  }, [data])

  const computed = useMemo(() => {
    if (!data) return null
    const names = new Map(data.districts.features.map((f) => [String(f.properties?.district), String(f.properties?.name ?? f.properties?.district)]))
    const totals = programTotals(data.projects)
    const spots = largestPlaced(data.projects, data.sites)
    const dm = districtMoney(data.projects, data.sites, data.counts, data.population, names)
    const byWhere = [...dm.rows].sort((a, b) => b.where / b.population - a.where / a.population)
    const top = byWhere.slice(0, 3)
    const leads = top.map((r) => leadProjectIn(r.district, data.projects, data.sites)).filter((s): s is Spot => !!s)
    const psa = megaProject('Penn Station Access', data.projects, data.sites, data.mega)
    const jails = boroughJails(data.projects)
    const jailSpots = jails.jails.map((j) => ({ ...j.spot, note: j.original ? `first recorded at ${money(j.original)}` : undefined }))
    const bld = buildings(data.projects)
    const said = statementsFor('Penn Station Access', data.statements)
    const dots = siteDots(data.projects, data.sites)
    const groups = siteGroups(dots)
    // The project plate's stations: the exported walk zones (names from psa_stations), else the project's sites.
    const reach = data.reach.filter((r) => r.mega_project === 'Penn Station Access')
    const stations = reach.length ? reach.map((r) => ({ lon: r.lon, lat: r.lat, place: r.station, residents: r.residents })) : psa.stations
    const placed = new Map(dots.map((d) => [d.id, d.tier]))
    const approx = [...placed.values()].filter((t) => t === 'B').length
    return { names, totals, spots, dm, leads, top, psa, said, jails, jailSpots, bld, groups, stations, placed: placed.size, approx }
  }, [data])

  const view: View = useMemo(() => {
    if (!computed) return { kind: 'builders', focus: null }
    if (active === 'resident') {
      const vals = computed.dm.rows.map((r) => ({ d: r.district, v: (step === 'where' ? r.where : r.serves) / r.population }))
      return { kind: 'districts', fills: quantileFills(vals), focus }
    }
    if (active === 'jails') return { kind: 'spots', focus }
    if (active === 'psa') return { kind: 'stations', stations: computed.stations, focus: null }
    return { kind: 'builders', focus }
  }, [computed, active, step, focus])

  const spotsOnMap = !computed ? [] : active === 'builders' ? computed.spots : active === 'jails' ? computed.jailSpots : active === 'resident' ? computed.leads : []
  const padding = phone ? { top: 70, right: 10, bottom: window.innerHeight * 0.42, left: 10 } : { top: 30, right: 30, bottom: 30, left: 30 }

  if (error) return <div className="story-state"><p>The data did not load: {error}</p><a href={TOOL}>Open the map instead</a></div>

  return (
    <div className="story">
      <div className="story-sheet">
        <StoryMap view={view} groups={computed?.groups ?? []} rail={data?.rail ?? null} districts={data?.districts ?? null} spots={spotsOnMap} padding={padding}
          highlight={active === 'builders' ? highlight : null} hot={hot} onHot={setHot} />
      </div>
      <aside className="story-column">
        <KeySheet active={active} stopped={stopped} boroughs={data?.boroughs ?? null} frame={active === 'psa' ? computed?.stations ?? null : null} phone={phone} />
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
              <JailsPlate jails={computed.jails} spots={computed.jailSpots} bld={computed.bld} focus={focus} onFocus={setFocus} hot={hot} onHot={setHot} />
            </Plate>

            <Plate id="resident" n={n('resident')} title="Per resident">
              <p className="lede">Divide the city's capital money by the people who live where it counts, and a few districts stand far apart.</p>
              <div className="steps" role="group" aria-label="Count money">
                <button type="button" aria-pressed={step === 'where'} onClick={() => setStep('where')}>Where the work is</button>
                <button type="button" aria-pressed={step === 'serves'} onClick={() => setStep('serves')}>Whom it serves</button>
              </div>
              <p className="step-note">
                {step === 'where'
                  ? 'Each project counts in the district where it is built, wherever its users live.'
                  : 'Each project counts in the area it is built for: a library in its district, a borough jail across its borough, a water tunnel across the whole city (which is left off the map).'}
              </p>
              <RampKey dm={computed.dm} step={step} />
              <Dumbbell dm={computed.dm} />
              <p>Counted where the work is, {listNames(computed.top.map((r) => r.name))} lead, each holding one very large project that serves far more people than live there. Counted by whom it serves, that money spreads across its borough or the city, and the districts draw closer.</p>
              <OnTheGround spots={computed.leads} focus={focus} onFocus={setFocus} hot={hot} onHot={setHot} caption="What puts the top three districts ahead" />
              {computed.leads.some((s) => s.id.startsWith('BBJ-')) && <p>Three of them are the borough-based jails of plate {n('jails')}: each serves its whole borough, so counted by whom it serves, its money spreads across the borough.</p>}
              <p className="estimate-note"><span className="est" aria-hidden="true" /> Hatched figures rest on this project's own estimate of the area each project serves, built from the city's Statement of Needs definitions and subway ridership. They are not official data.</p>
              <Sources text="City capital projects; 2020 census population by tract; community district names from City Planning." />
            </Plate>

            <Plate id="psa" n={n('psa')} title="Penn Station Access">
              <ProjectPlate psa={computed.psa} said={computed.said} stations={computed.stations} />
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

function Plate({ id, n, title, children }: { id: PlateId; n: number; title: string; children: React.ReactNode }) {
  return (
    <section className="plate" id={`plate-${id}`} aria-labelledby={`h-${id}`}>
      <h2 id={`h-${id}`} className="plate-title"><span className="plate-no" aria-label={`Plate ${n}`}>{n}</span>{title}</h2>
      {children}
    </section>
  )
}

function KeySheet({ active, stopped, boroughs, frame, phone }: { active: PlateId; stopped: PlateId | null; boroughs: FeatureCollection | null; frame: { lon: number; lat: number }[] | null; phone: boolean }) {
  const go = (id: PlateId) => document.getElementById(`plate-${id}`)?.scrollIntoView({ behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' })
  const n = PLATES.find((p) => p.id === active)?.n ?? 1
  return (
    <nav className="key" aria-label="Plates">
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
      <a className="skip" href={TOOL}>Skip to the map</a>
    </nav>
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
    <svg className="keymap" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Key map: plate ${n} covers ${frame ? 'part of the Bronx' : 'the whole city'}`}>
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
  const W = 420, L = 196, R = 14, rowH = 26, rDot = 5.5
  const x = (v: number) => L + (v / max) * (W - L - R)
  return (
    <figure className="dumbbell">
      <figcaption>The ten districts that change most between the two counts, money per resident</figcaption>
      <svg viewBox={`0 0 ${W} ${rows.length * rowH + 26}`} role="img" aria-label="Money per resident, counted where the work is and by whom it serves">
        <defs>
          <pattern id="hatch" width="4" height="4" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="4" height="4" fill="#ffffff" /><rect width="2" height="4" fill="#2a78d6" /></pattern>
          <marker id="db-arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0.5L8,4L0,7.5Z" className="db-head" /></marker>
        </defs>
        {rows.map((r, i) => {
          const y = i * rowH + 14
          const dir = Math.sign(r.b - r.a), end = x(r.b) - dir * (rDot + 1.5)
          return (
            <g key={r.district}>
              <title>{`${r.name}: ${perResident(r.a)} where the work is, ${perResident(r.b)} by whom it serves (estimate)`}</title>
              <text x={L - 8} y={y + 4} className="db-name">{r.name.length > 30 ? r.name.slice(0, 29) + '…' : r.name}</text>
              {Math.abs(end - x(r.a)) > 6 && <line x1={x(r.a)} x2={end} y1={y} y2={y} className="db-link" markerEnd="url(#db-arrow)" />}
              <circle cx={x(r.a)} cy={y} r={4} className="db-where" />
              <circle cx={x(r.b)} cy={y} r={rDot} fill="url(#hatch)" className="db-serves" />
            </g>
          )
        })}
        <text x={L} y={rows.length * rowH + 22} className="db-axis">$0</text>
        <text x={W - R} y={rows.length * rowH + 22} className="db-axis" textAnchor="end">{perResident(max)}</text>
      </svg>
      <div className="db-key"><span><i className="k-where" />where the work is</span><span aria-hidden="true">→</span><span><i className="k-serves" />whom it serves (estimate)</span></div>
    </figure>
  )
}

/** Published commentary and analysis a plate cites: who, what, when, what kind, and whether it was read in full. */
interface Cite { publisher: string; title: string; date: string; url: string; kind: 'official' | 'research' | 'press' }
const JAIL_CITES: Cite[] = [
  { publisher: 'Queens Daily Eagle', title: 'Borough-based jail costs double to $16 billion, mayor claims', date: 'April 25, 2024', url: 'https://queenseagle.com/all/2024/4/25/borough-based-jail-costs-double-to-16-billion-mayor-claims', kind: 'press' },
  { publisher: 'New York City Comptroller', title: 'Cost of Incarceration per Person in New York City Skyrockets to All-Time High', date: 'December 6, 2021', url: 'https://comptroller.nyc.gov/newsroom/comptroller-stringer-cost-of-incarceration-per-person-in-new-york-city-skyrockets-to-all-time-high-2', kind: 'official' },
  { publisher: 'CUNY Institute for State and Local Governance', title: 'Closing Rikers Cannot Wait', date: 'October 12 (year not given)', url: 'https://islg.cuny.edu/blog/closing-rikers-cannot-wait', kind: 'research' },
]

function JailsPlate({ jails, spots, bld, focus, onFocus, hot, onHot }: { jails: ReturnType<typeof boroughJails>; spots: Spot[]; bld: ReturnType<typeof buildings>; focus: Spot | null; onFocus: (s: Spot | null) => void; hot: string | null; onHot: (id: string | null) => void }) {
  const when = jails.originalPeriod ? `${MONTHS[(jails.originalPeriod % 100) - 1]} ${Math.floor(jails.originalPeriod / 100)}` : 'first recorded'
  const places = bld.places.reduce((t, p) => t + p.budget, 0)
  return (
    <>
      <p className="lede">The city is building {["no", "one", "two", "three", "four", "five", "six"][jails.projects] ?? jails.projects} jails, in Brooklyn, Queens, the Bronx and Manhattan, to replace the jails on Rikers Island, which city law says must close in 2027.</p>
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
      <BuildingsChart bld={bld} original={jails.original} when={when} />
      <p>The four jails hold {money(jails.budget)}, against {money(jails.original)} when first recorded in {when}: most of the {money(bld.corrections)} the city has in jails and corrections, more than its libraries, cultural institutions, police, fire and EMS, shelters and older adults' centers together ({money(places)}), and more than every park ({money(bld.parks)}).</p>
      <p>Each record is scheduled in stages: one clears what stands on the site (the city's reports spell it "Dismantal"), the other builds the new jail; Queens's also lays a water main.</p>
      <p>Building them is one cost. Published analysis adds two more: running a jail cost $556,539 per person in fiscal 2021, counting fringe benefits and health care (the City Comptroller), and a smaller system running at its target of 3,300 people could save nearly $2 billion a year (CUNY's Institute for State and Local Governance). The first jail, Brooklyn's, is not expected to open until 2029 (Queens Daily Eagle, April 2024).</p>
      <Cites cites={JAIL_CITES} />
      <Sources text="City capital projects: each jail's design-build record (BBJ-K, -M, -Q, -X), its first budget recorded (Open Data qj5n-h5qp) and spending to date; stage names from the Capital Projects Dashboard. Nominal dollars." />
    </>
  )
}

/** Three bars on one scale: jails and corrections (the borough-based jails within it, their first recorded budget
 * marked), the places people use stacked, and parks. */
function BuildingsChart({ bld, original, when }: { bld: ReturnType<typeof buildings>; original: number; when: string }) {
  const W = 420, L = 0, R = 64, barH = 18, gap = 46
  const max = Math.max(bld.corrections, bld.places.reduce((t, p) => t + p.budget, 0), bld.parks)
  const x = (v: number) => L + (v / max) * (W - L - R)
  const starts = bld.places.map((_, i) => bld.places.slice(0, i).reduce((t, p) => t + p.budget, 0))
  const acc = bld.places.reduce((t, p) => t + p.budget, 0)
  const stack = bld.places.map((p, i) => ({ ...p, x0: x(starts[i]), x1: x(starts[i] + p.budget), i }))
  const rows = [
    { label: 'Jails and corrections', total: bld.corrections },
    { label: 'Libraries, culture, police, fire and EMS, shelters, older adults', total: acc },
    { label: 'Parks', total: bld.parks },
  ]
  return (
    <figure className="bars">
      <figcaption>Unfinished city capital money</figcaption>
      <svg viewBox={`0 0 ${W} ${rows.length * gap + 6}`} role="img" aria-label={rows.map((r) => `${r.label}: ${money(r.total)}`).join('; ')}>
        {rows.map((r, i) => <text key={r.label} x={0} y={i * gap + 12} className="bars-label">{r.label}</text>)}
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

function ProjectPlate({ psa, said, stations }: { psa: ReturnType<typeof megaProject>; said: Map<string, Statement>; stations: { place: string | null; residents?: number }[] }) {
  const first = psa.series[0], last = psa.series.at(-1)
  const lead = psa.work[0]
  const done = said.get('substantial_completion'), temp = said.get('temporary_service')
  const out1 = said.get('outages_first_year'), out2 = said.get('outages_second_year')
  const doc = done ?? temp
  const pages = [...new Set([...said.values()].flatMap((r) => [...r.quote.matchAll(/(?:^| \| )p(\d+):/g)].map((m) => Number(m[1]))))].sort((a, b) => a - b)
  return (
    <>
      <p className="lede">{stations.length} new Metro-North stations in the East Bronx, on the Amtrak line that carries trains past them today.</p>
      {stations.some((s) => s.residents !== undefined) && <WalkZones stations={stations} />}
      {first && last && <Series series={psa.series} />}
      <p>MTA's money for the project{first && last ? ` went from ${money(first.total)} in ${month(first.load)} to ${money(last.total)} in ${month(last.load)}` : ''}, across {psa.lines.length} budget lines.{lead ? ` The largest, a ${money(lead.budget)} design-build contract, rebuilds the Amtrak line the trains will run on${said.has('budget_majority') ? ", and MTA says most of the project's money goes to that rebuilding" : ''}.` : ''}</p>
      <WorkLedger work={psa.work} />
      {lead && last && (
        <p>
          The {month(last.load)} dashboard {done ? 'still dates' : 'dates'} the {shortLine(lead.title).toLowerCase()} {lead.finish ? month(lead.finish) : 'undated'}{lead.pctComplete !== null ? `, ${lead.pctComplete}% complete` : ''}.
          {done && ` In ${month(done.statement_date)} MTA told the ${done.setting} that substantial completion had moved to ${quarterLabel(done.value)}${temp ? `, with temporary service possible from ${temp.value}` : ''}${out1 && out2 ? `, and laid the delay on Amtrak: ${out1.value} promised weekend track outages in the first year, ${out2.value} in the second` : ''}.`}
        </p>
      )}
      <p className="sources">
        MTA Capital Dashboard (every quarterly load since March 2020)
        {doc && <>; MTA, <a href={doc.url}>presentation to the {doc.setting}, {month(doc.statement_date)}</a> ({pages.length > 1 ? 'pp.' : 'p.'} {pages.join(', ')})</>}
        ; station sites from the project's Environmental Assessment (May 2021); route from MTA's rail branches and the city's railroad layer; residents within 800 m from the 2020 census, an estimate. Nominal dollars.
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

/** The project's budget lines, largest first: money, share complete and the dashboard's finish. */
function WorkLedger({ work }: { work: ReturnType<typeof megaProject>['work'] }) {
  const shown = work.slice(0, 6), rest = work.slice(6)
  return (
    <table className="work">
      <caption>The work, line by line</caption>
      <thead><tr><th scope="col">Budget line</th><th scope="col">Money</th><th scope="col">Done</th><th scope="col">Due</th></tr></thead>
      <tbody>
        {shown.map((w) => (
          <tr key={w.id}>
            <th scope="row">{shortLine(w.title)}</th>
            <td className="num">{money(w.budget)}</td>
            <td><span className="done" aria-label={w.pctComplete === null ? 'not published' : `${w.pctComplete}%`}><i style={{ width: `${w.pctComplete ?? 0}%` }} /></span></td>
            <td className="num">{w.finish ? (w.finish.length > 4 ? `${MONTHS[Number(w.finish.slice(5, 7)) - 1].slice(0, 3)} ${w.finish.slice(0, 4)}` : w.finish) : '—'}</td>
          </tr>
        ))}
        {rest.length > 0 && <tr className="rest"><th scope="row">{rest.length} smaller lines</th><td className="num">{money(rest.reduce((t, w) => t + w.budget, 0))}</td><td /><td /></tr>}
      </tbody>
    </table>
  )
}

function Series({ series }: { series: { load: string; total: number }[] }) {
  const W = 360, H = 150, L = 46, B = 22, T = 10
  const xs = series.map((_, i) => L + (i / Math.max(1, series.length - 1)) * (W - L - 10))
  const max = Math.max(...series.map((s) => s.total))
  const y = (v: number) => T + (1 - v / max) * (H - T - B)
  const d = series.map((s, i) => `${i ? 'L' : 'M'}${xs[i].toFixed(1)},${y(s.total).toFixed(1)}`).join('')
  const last = series.length - 1
  return (
    <figure className="series">
      <figcaption>MTA money for Penn Station Access, each quarterly report</figcaption>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Money for Penn Station Access by quarterly report">
        <line x1={L} x2={W - 10} y1={y(0)} y2={y(0)} className="axis" />
        <text x={L - 6} y={y(max) + 4} className="tick" textAnchor="end">{money(max)}</text>
        <text x={L - 6} y={y(0) + 4} className="tick" textAnchor="end">$0</text>
        <path d={`${d}L${xs[last]},${y(0)}L${xs[0]},${y(0)}Z`} className="series-area" />
        <path d={d} className="series-line" />
        {series.map((s, i) => <circle key={s.load} cx={xs[i]} cy={y(s.total)} r={3} className="series-dot"><title>{`${s.load.slice(0, 7)}: ${money(s.total)}`}</title></circle>)}
        <text x={xs[0]} y={H - 6} className="tick">{series[0].load.slice(0, 4)}</text>
        <text x={xs[last]} y={H - 6} className="tick" textAnchor="end">{series[last].load.slice(0, 4)}</text>
      </svg>
    </figure>
  )
}

function Sources({ text }: { text: string }) {
  return <p className="sources">{text}</p>
}

function listNames(names: string[]): string {
  return names.length < 2 ? names.join('') : `${names.slice(0, -1).join(', ')} and ${names.at(-1)}`
}

function month(ym: string): string {
  return `${MONTHS[Number(ym.slice(5, 7)) - 1]} ${ym.slice(0, 4)}`
}

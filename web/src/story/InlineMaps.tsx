import { geoIdentity, geoPath } from 'd3-geo'
import type { Feature, FeatureCollection, Geometry, Position } from 'geojson'
import { useEffect, useMemo, useRef } from 'react'
import { money, PEOPLE, perResident, PROGRAMS, type DistrictRow, type Jail, type ProgramTotal, type SiteGroup, type Spot } from './plates'
import { useWidth } from './useWidth'

/** Inline maps: figures drawn for one point each, in the atlas's paper and ink, set in the text like the charts. */

const WATER = '#d5e2e8'

/** Web Mercator in radians, so outlines draw flat (geoIdentity) whatever way their rings wind. */
const merc = ([lon, lat]: Position): Position => [(lon * Math.PI) / 180, -Math.log(Math.tan(Math.PI / 4 + (lat * Math.PI) / 360))]
function project<G extends Geometry>(g: G): G {
  const ring = (r: Position[]) => r.map(merc)
  switch (g.type) {
    case 'Point': return { ...g, coordinates: merc(g.coordinates) }
    case 'LineString': case 'MultiPoint': return { ...g, coordinates: ring(g.coordinates) }
    case 'Polygon': case 'MultiLineString': return { ...g, coordinates: g.coordinates.map(ring) }
    case 'MultiPolygon': return { ...g, coordinates: g.coordinates.map((p) => p.map(ring)) }
    default: return g
  }
}
const flat = <F extends Feature>(f: F): F => ({ ...f, geometry: project(f.geometry) })

/** Every outer and inner ring of a (multi)polygon, as given. */
const rings = (g: Geometry): Position[][] => (g.type === 'Polygon' ? g.coordinates : g.type === 'MultiPolygon' ? g.coordinates.flat() : [])
/** Even-odd ray casting over all rings, in screen pixels. */
function inside([x, y]: number[], rs: number[][][]) {
  let c = false
  for (const r of rs) for (let i = 0, j = r.length - 1; i < r.length; j = i++) {
    const [xi, yi] = r[i], [xj, yj] = r[j]
    if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) c = !c
  }
  return c
}
/** Where to letter an area within the frame: the middle of the grid points that fall on it, kept clear of the edges;
 * none when too little of it shows. */
function labelPoint(rs: number[][][], W: number, H: number): number[] | null {
  const pts: number[][] = []
  for (let gx = 0; gx <= 14; gx++) for (let gy = 0; gy <= 14; gy++) {
    const p = [44 + (gx * (W - 88)) / 14, 40 + (gy * (H - 80)) / 14]
    if (inside(p, rs)) pts.push(p)
  }
  if (pts.length < 6) return null
  const mid = [pts.reduce((t, p) => t + p[0], 0) / pts.length, pts.reduce((t, p) => t + p[1], 0) / pts.length]
  return inside(mid, rs) ? mid : pts.reduce((b, p) => (Math.hypot(p[0] - mid[0], p[1] - mid[1]) < Math.hypot(b[0] - mid[0], b[1] - mid[1]) ? p : b))
}
const point = (lon: number, lat: number): Feature => ({ type: 'Feature', properties: {}, geometry: { type: 'Point', coordinates: merc([lon, lat]) } })

/** The four borough-based jails around Rikers Island (DCP's 2020 neighborhood area QN0151): each jail a numbered
 * marker, ringed in its borough's tint as in the plate's list; choosing one on the map or in the list reads it out. */
export function JailsMap({ jails, boroughs, rikers, tints, focus, onFocus }: {
  jails: Jail[]; boroughs: FeatureCollection; rikers: Feature | null; tints: Record<string, string>
  focus: Spot | null; onFocus: (s: Spot | null) => void
}) {
  const [ref, W] = useWidth()
  const H = Math.round(Math.min(W * 1.05, 520))
  const land = useMemo(() => boroughs.features.map(flat), [boroughs])
  const island = useMemo(() => (rikers ? flat(rikers) : null), [rikers])
  const { proj, path, at } = useMemo(() => {
    const frame: FeatureCollection = { type: 'FeatureCollection', features: [...jails.map((j) => point(j.spot.lon, j.spot.lat)), ...(island ? [island] : [])] }
    const proj = geoIdentity().fitExtent([[56, 56], [W - 56, H - 48]], frame)
    return { proj, path: geoPath(proj), at: (lon: number, lat: number) => proj(merc([lon, lat]) as [number, number]) as [number, number] }
  }, [jails, island, W, H])
  const shapes = useMemo(() => land.map((f) => {
    const rs = rings(f.geometry).map((r) => r.map((p) => proj(p as [number, number]) as number[]))
    return { name: String(f.properties?.borough), d: path(f) ?? '', c: labelPoint(rs, W, H) }
  }), [land, path, proj, W, H])
  const rk = island ? path.centroid(island) : null
  const chosen = jails.find((j) => j.spot.id === focus?.id) ?? null
  return (
    <figure className="inline-map" ref={ref as React.RefObject<HTMLElement>}>
      <figcaption>The four new jails and Rikers Island, the jails they replace; choose a jail to read its figures</figcaption>
      <svg viewBox={`0 0 ${W} ${H}`} width={W} height={H} role="group" aria-label="Map of the four borough-based jails and Rikers Island">
        <rect width={W} height={H} fill={WATER} />
        {shapes.map((s) => <path key={s.name} d={s.d} className="im-land" />)}
        {island && <path d={path(island) ?? ''} className="im-rikers" />}
        {shapes.map((s) => s.c && <text key={s.name} x={s.c[0]} y={s.c[1]} className="im-borough" textAnchor="middle">{s.name === 'Bronx' ? 'The Bronx' : s.name}</text>)}
        {rk && <text x={rk[0]} y={rk[1] + 30} className="im-label" textAnchor="middle">Rikers Island</text>}
        {jails.map((j, i) => {
          const [x, y] = at(j.spot.lon, j.spot.lat)
          const on = chosen?.spot.id === j.spot.id
          return (
            <g key={j.spot.id} className={on ? 'im-jail on' : 'im-jail'} transform={`translate(${x},${y})`} role="button" tabIndex={0}
              aria-pressed={on} aria-label={`${j.borough}: ${money(j.budget)}`}
              onClick={() => onFocus(on ? null : j.spot)} onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onFocus(on ? null : j.spot) } }}>
              <circle r={22} className="im-hit" />
              <circle r={on ? 14 : 12} className="im-disc" style={{ stroke: tints[j.borough ?? ''] ?? 'var(--ink)' }} />
              <text y={4.5} textAnchor="middle" className="im-no">{i + 1}</text>
            </g>
          )
        })}
      </svg>
      <p className="im-read" aria-live="polite">
        {chosen
          ? <><b>{chosen.borough}</b>, {chosen.spot.place}: {money(chosen.budget)} now, {money(chosen.spent)} spent ({Math.round((100 * chosen.spent) / chosen.budget)}%){chosen.original ? `, ${money(chosen.original)} when first recorded` : ''}.</>
          : 'Choose a jail on the map or in the list below.'}
      </p>
    </figure>
  )
}

/** A frame fitted to some features: the projection, its path, a lon/lat-to-pixel function and pixels per mercator unit. */
function useFrame(fit: Feature[], W: number, H: number, pad: [number, number, number, number]) {
  return useMemo(() => {
    const proj = geoIdentity().fitExtent([[pad[3], pad[0]], [W - pad[1], H - pad[2]]], { type: 'FeatureCollection', features: fit })
    return { proj, path: geoPath(proj), at: (lon: number, lat: number) => proj(merc([lon, lat]) as [number, number]) as [number, number], k: proj.scale() }
  }, [fit, W, H, pad])
}
const PAD_SMALL: [number, number, number, number] = [6, 6, 6, 6]

/** The story map's dot size: radius on the square root of a point's money in $M (StoryMap's stops), scaled. */
const STOPS = [[0, 1.8], [2, 3], [8, 5], [20, 9], [43, 14], [67, 16]]
function dotRadius(dollars: number, scale: number) {
  const v = Math.sqrt(Math.max(0, dollars) / 1e6)
  for (let i = 1; i < STOPS.length; i++) {
    const [x0, r0] = STOPS[i - 1], [x1, r1] = STOPS[i]
    if (v <= x1) return scale * (r0 + ((r1 - r0) * (v - x0)) / (x1 - x0))
  }
  return scale * STOPS.at(-1)![1]
}

/** Three small maps of the city, one per builder: its open work at each place, sized by money and tinted as the
 * builder, with its largest project at one known address numbered as in the plate's list. A map and the builder's row
 * in the table light each other. */
export function BuildersMaps({ groups, boroughs, totals, spots, highlight, onHighlight, focus, onFocus }: {
  groups: SiteGroup[]; boroughs: FeatureCollection; totals: ProgramTotal[]; spots: Spot[]
  highlight: string | null; onHighlight: (id: string | null) => void; focus: Spot | null; onFocus: (s: Spot | null) => void
}) {
  const [ref, W] = useWidth()
  const cols = W >= 520 ? 3 : 2, gap = 10
  const mw = Math.floor((W - gap * (cols - 1)) / cols), mh = Math.round(mw * 1.02)
  const land = useMemo(() => boroughs.features.map(flat), [boroughs])
  const { path, at } = useFrame(land, mw, mh, PAD_SMALL)
  const chosen = spots.find((s) => s.id === focus?.id) ?? null
  return (
    <figure className="inline-map builders-maps" ref={ref as React.RefObject<HTMLElement>}>
      <figcaption>Each builder's open work, sized by money at each place; choose a numbered project</figcaption>
      <div className="bm-grid" style={{ gridTemplateColumns: `repeat(${cols}, ${mw}px)`, gap }}>
        {PROGRAMS.map((p) => {
          const t = totals.find((x) => x.id === p.id)
          const i = spots.findIndex((s) => s.program === p.id), spot = spots[i]
          const xy = spot ? at(spot.lon, spot.lat) : null
          return (
            <div key={p.id} className={highlight === p.id ? 'bm on' : 'bm'} onMouseEnter={() => onHighlight(p.id)} onMouseLeave={() => onHighlight(null)}>
              <p className="bm-head"><i className="swatch" style={{ background: p.tint }} />{p.short}{t ? <span> {t.projects.toLocaleString()} · {money(t.budget)}</span> : null}</p>
              <div className="bm-map" style={{ width: mw, height: mh }}>
                <DotCanvas groups={groups} program={p.id} tint={p.tint} land={land} path={path} at={at} W={mw} H={mh} />
                {spot && xy && (
                  <svg className="bm-over" viewBox={`0 0 ${mw} ${mh}`} width={mw} height={mh}>
                    <g className={chosen?.id === spot.id ? 'im-jail on' : 'im-jail'} transform={`translate(${xy[0]},${xy[1]})`} role="button" tabIndex={0}
                      aria-pressed={chosen?.id === spot.id} aria-label={`${spot.title}: ${money(spot.budget)}`}
                      onClick={() => onFocus(chosen?.id === spot.id ? null : spot)}
                      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onFocus(chosen?.id === spot.id ? null : spot) } }}>
                      <circle r={18} className="im-hit" />
                      <circle r={10} className="im-disc" style={{ stroke: p.tint }} />
                      <text y={4} textAnchor="middle" className="im-no small">{i + 1}</text>
                    </g>
                  </svg>
                )}
              </div>
            </div>
          )
        })}
      </div>
      <p className="im-read" aria-live="polite">
        {chosen ? <><b>{chosen.title}</b>: {money(chosen.budget)}{chosen.place ? `, ${chosen.place}` : ''}.</> : 'Choose a numbered project, or a map to find its builder in the table.'}
      </p>
    </figure>
  )
}

/** One builder's dots, on a canvas (thousands of points): the land, then dots largest first so small ones stay seen. */
function DotCanvas({ groups, program, tint, land, path, at, W, H }: {
  groups: SiteGroup[]; program: string; tint: string; land: Feature[]; path: ReturnType<typeof geoPath>
  at: (lon: number, lat: number) => [number, number]; W: number; H: number
}) {
  const ref = useRef<HTMLCanvasElement>(null)
  useEffect(() => {
    const c = ref.current
    if (!c) return
    const dpr = window.devicePixelRatio || 1
    c.width = W * dpr; c.height = H * dpr
    const ctx = c.getContext('2d')!
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    ctx.fillStyle = WATER; ctx.fillRect(0, 0, W, H)
    const draw = geoPath(path.projection() as never, ctx)
    ctx.fillStyle = '#ffffff'; ctx.strokeStyle = '#9aa5b1'; ctx.lineWidth = 0.5
    for (const f of land) { ctx.beginPath(); draw(f); ctx.fill(); ctx.stroke() }
    const dots = groups.filter((g) => (g.byProgram[program] ?? 0) > 0)
      .map((g) => ({ xy: at(g.lon, g.lat), r: dotRadius(g.byProgram[program], 0.42) }))
      .sort((a, b) => b.r - a.r)
    ctx.fillStyle = tint; ctx.strokeStyle = '#ffffff'; ctx.lineWidth = 0.4; ctx.globalAlpha = 0.85
    for (const d of dots) { ctx.beginPath(); ctx.arc(d.xy[0], d.xy[1], Math.max(0.8, d.r), 0, 2 * Math.PI); ctx.fill(); if (d.r > 2) ctx.stroke() }
    ctx.globalAlpha = 1
  }, [groups, program, tint, land, path, at, W, H])
  return <canvas ref={ref} style={{ width: W, height: H }} aria-hidden="true" />
}

/** The community districts shaded by money per resident (the plate's ramp, by its step); a district and its line in
 * the rank chart light each other, and the one chosen is read out. */
export function DistrictMap({ districts, boroughs, rows, fills, step, hot, onHot }: {
  districts: FeatureCollection; boroughs: FeatureCollection; rows: DistrictRow[]; fills: Map<string, string>
  step: 'where' | 'serves'; hot: string | null; onHot: (d: string | null) => void
}) {
  const [ref, W] = useWidth()
  const H = Math.round(Math.min(W * 1.0, 540))
  const land = useMemo(() => boroughs.features.map(flat), [boroughs])
  const shapes = useMemo(() => districts.features.map(flat), [districts])
  const { path } = useFrame(land, W, H, [12, 12, 12, 12])
  const landD = useMemo(() => land.map((f) => path(f) ?? ''), [land, path])
  const dists = useMemo(() => shapes.map((f) => ({ id: String(f.properties?.district), d: path(f) ?? '' })), [shapes, path])
  const row = rows.find((r) => r.district === hot) ?? null
  const v = row ? (step === 'where' ? row.where : row.serves) / row.population : 0
  return (
    <figure className="inline-map" ref={ref as React.RefObject<HTMLElement>}>
      <figcaption>Money per resident in each community district, {step === 'where' ? 'where the work is' : 'by whom it serves (an estimate)'}</figcaption>
      <svg viewBox={`0 0 ${W} ${H}`} width={W} height={H} role="group" aria-label="Map of community districts by money per resident" onMouseLeave={() => onHot(null)}>
        <rect width={W} height={H} fill={WATER} />
        {landD.map((d, i) => <path key={i} d={d} className="im-land" />)}
        {dists.map((x) => (
          <path key={x.id} d={x.d} className={hot === x.id ? 'im-district on' : 'im-district'} style={{ fill: fills.get(x.id) ?? '#f3f5f4' }}
            onMouseEnter={() => onHot(x.id)} onClick={() => onHot(hot === x.id ? null : x.id)} />
        ))}
        {dists.filter((x) => x.id === hot).map((x) => <path key="hot" d={x.d} className="im-district-hot" />)}
      </svg>
      <p className="im-read" aria-live="polite">
        {row ? <><b>{row.name}</b>: {perResident(v)} per resident{step === 'serves' ? ' (an estimate)' : ''}.</> : 'Choose a district on the map or in the chart.'}
      </p>
    </figure>
  )
}

/** Penn Station Access: the route (red) over Metro-North's lines, Penn Station and Grand Central, and the four new
 * stations with their 800 m walk zones shaded by the residents in them (an estimate); a station chosen is read out. */
export function PsaMap({ rail, boroughs, stations, chosen, onChoose }: {
  rail: FeatureCollection; boroughs: FeatureCollection; stations: { lon: number; lat: number; place: string | null; residents?: number }[]
  chosen: string | null; onChoose: (place: string | null) => void
}) {
  const [ref, W] = useWidth()
  const H = Math.round(Math.min(W * 0.95, 520))
  const land = useMemo(() => boroughs.features.map(flat), [boroughs])
  const lines = useMemo(() => rail.features.filter((f) => f.geometry.type !== 'Point').map(flat), [rail])
  const terminals = useMemo(() => rail.features.filter((f) => f.properties?.line === 'terminal' && f.geometry.type === 'Point'), [rail])
  const fit = useMemo(() => [...stations.map((s) => point(s.lon, s.lat)), ...terminals.map(flat)], [stations, terminals])
  const { path, at, k } = useFrame(fit, W, H, [34, 70, 34, 34])
  const landD = useMemo(() => land.map((f) => path(f) ?? ''), [land, path])
  const people = (n = 0) => [...PEOPLE].reverse().find(([v]) => n >= v)?.[1] ?? PEOPLE[0][1]
  const one = stations.find((s) => s.place === chosen) ?? null
  return (
    <figure className="inline-map" ref={ref as React.RefObject<HTMLElement>}>
      <figcaption>The route from Penn Station to the four new Bronx stations, each with the residents within 800 m (an estimate); choose a station</figcaption>
      <svg viewBox={`0 0 ${W} ${H}`} width={W} height={H} role="group" aria-label="Map of the Penn Station Access route and stations">
        <rect width={W} height={H} fill={WATER} />
        {landD.map((d, i) => <path key={i} d={d} className="im-land" />)}
        {stations.map((s) => {
          const [x, y] = at(s.lon, s.lat)
          const r = (800 / (6371008 * Math.cos((s.lat * Math.PI) / 180))) * k
          return <circle key={`z${s.place}`} cx={x} cy={y} r={r} className="im-zone" style={{ fill: people(s.residents) }} />
        })}
        {lines.filter((f) => f.properties?.line !== 'Penn Station Access').map((f, i) => <path key={i} d={path(f) ?? ''} className="im-rail" />)}
        {lines.filter((f) => f.properties?.line === 'Penn Station Access').map((f, i) => <g key={i}><path d={path(f) ?? ''} className="im-route-case" /><path d={path(f) ?? ''} className="im-route" /></g>)}
        {terminals.map((f) => {
          const [lon, lat] = (f.geometry as GeoJSON.Point).coordinates
          const [x, y] = at(lon, lat)
          // Penn Station sits just south-west of Grand Central: letter one above its point and the other below.
          const name = String(f.properties?.name), below = name === 'Penn Station'
          return <g key={name} transform={`translate(${x},${y})`}><circle r={4.5} className="im-terminal" /><text x={8} y={below ? 15 : -7} className="im-label small">{name}</text></g>
        })}
        {stations.map((s) => {
          const [x, y] = at(s.lon, s.lat)
          const on = chosen === s.place
          return (
            <g key={s.place} className={on ? 'im-station on' : 'im-station'} transform={`translate(${x},${y})`} role="button" tabIndex={0} aria-pressed={on}
              aria-label={`${s.place}: about ${(s.residents ?? 0).toLocaleString()} residents within 800 m`}
              onClick={() => onChoose(on ? null : s.place)} onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onChoose(on ? null : s.place) } }}>
              <circle r={16} className="im-hit" />
              <circle r={on ? 7 : 5.5} className="im-stop" />
              <text x={9} y={-8} className="im-label small">{s.place}</text>
            </g>
          )
        })}
      </svg>
      <p className="im-read" aria-live="polite">
        {one ? <><b>{one.place}</b>: about {(one.residents ?? 0).toLocaleString()} residents within 800 m, about a ten-minute walk (an estimate).</> : 'Choose a station to read the residents within a ten-minute walk.'}
      </p>
    </figure>
  )
}

/** All three builders on one map of the city, for a plate read beside it: each place's dot sized by its money and
 * tinted by the builder with most of it, and each builder's largest project at one known address numbered. A lit
 * builder keeps its tint and its largest project while the rest fade. Each state is drawn on one of two stacked
 * canvases and faded in over the other, so the colours change gradually. */
export function CityMap({ groups, boroughs, spots, highlight, onHighlight }: {
  groups: SiteGroup[]; boroughs: FeatureCollection; spots: Spot[]; highlight: string | null; onHighlight: (id: string | null) => void
}) {
  const [ref, W] = useWidth()
  const H = Math.round(Math.min(W * 1.0, 560))
  const land = useMemo(() => boroughs.features.map(flat), [boroughs])
  const { path, at } = useFrame(land, W, H, [10, 10, 10, 10])
  const c0 = useRef<HTMLCanvasElement>(null), c1 = useRef<HTMLCanvasElement>(null)
  const front = useRef(0)
  const drawn = useRef<string | null>(null)
  const tintOfProgram = (id: string) => PROGRAMS.find((p) => p.id === id)?.tint ?? '#7b8494'
  const dots = useMemo(() => groups.map((g) => ({ xy: at(g.lon, g.lat), g })).sort((a, b) => b.g.budget - a.g.budget), [groups, at])

  useEffect(() => {
    const key = `${highlight ?? ''}|${W}|${H}|${dots.length}`
    if (drawn.current === key) return
    // The first drawing goes on the front canvas; each later state on the back one, which then fades in.
    const layers = [c0.current, c1.current]
    const target = drawn.current === null ? front.current : 1 - front.current
    const c = layers[target]
    if (!c) return
    drawn.current = key
    const dpr = window.devicePixelRatio || 1
    c.width = W * dpr; c.height = H * dpr
    const ctx = c.getContext('2d')!
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    ctx.fillStyle = WATER; ctx.fillRect(0, 0, W, H)
    const draw = geoPath(path.projection() as never, ctx)
    ctx.fillStyle = '#ffffff'; ctx.strokeStyle = '#9aa5b1'; ctx.lineWidth = 0.6
    for (const f of land) { ctx.beginPath(); draw(f); ctx.fill(); ctx.stroke() }
    for (const { xy, g } of dots) {
      const lit = !highlight || (g.byProgram[highlight] ?? 0) > 0
      const amount = highlight && lit ? g.byProgram[highlight] : g.budget
      ctx.globalAlpha = highlight && !lit ? 0.35 : 0.88
      ctx.fillStyle = highlight ? (lit ? tintOfProgram(highlight) : '#c5ccd4') : tintOfProgram(g.lead)
      ctx.beginPath(); ctx.arc(xy[0], xy[1], Math.max(0.9, dotRadius(amount, 0.55)), 0, 2 * Math.PI); ctx.fill()
    }
    ctx.globalAlpha = 1
    front.current = target
    layers.forEach((l, i) => l?.classList.toggle('on', i === target))
  }, [highlight, W, H, dots, land, path])

  const caption = highlight ? `${PROGRAMS.find((p) => p.id === highlight)?.label}: its open work, and its largest project at one known address` : 'Open work of all three builders, each place tinted by the builder with most of the money there'
  return (
    <figure className="inline-map city-map" ref={ref as React.RefObject<HTMLElement>}>
      <figcaption>{caption}</figcaption>
      <div className="cm-map" style={{ width: W, height: H }}>
        <canvas ref={c0} className="cm-layer" style={{ width: W, height: H }} aria-hidden="true" />
        <canvas ref={c1} className="cm-layer" style={{ width: W, height: H }} aria-hidden="true" />
        <svg className="bm-over" viewBox={`0 0 ${W} ${H}`} width={W} height={H} role="group" aria-label="Map of the three builders' open projects">
          {spots.map((sp, i) => {
            const [x, y] = at(sp.lon, sp.lat)
            const on = highlight === sp.program, faded = highlight !== null && !on
            return (
              <g key={sp.id} className={`im-jail${on ? ' on' : ''}${faded ? ' faded' : ''}`} transform={`translate(${x},${y})`} role="button" tabIndex={0} aria-pressed={on}
                aria-label={`${sp.title}: ${money(sp.budget)}`} onClick={() => onHighlight(on ? null : sp.program)}
                onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onHighlight(on ? null : sp.program) } }}>
                <circle r={18} className="im-hit" />
                <circle r={on ? 13 : 11} className="im-disc" style={{ stroke: tintOfProgram(sp.program) }} />
                <text y={4.5} textAnchor="middle" className="im-no">{i + 1}</text>
              </g>
            )
          })}
        </svg>
      </div>
    </figure>
  )
}

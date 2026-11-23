import { geoIdentity, geoPath } from 'd3-geo'
import type { Feature, FeatureCollection, Geometry, Position } from 'geojson'
import { useMemo } from 'react'
import { money, type Jail, type Spot } from './plates'
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

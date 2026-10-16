import type { Feature, FeatureCollection } from 'geojson'
import type * as maplibregl from 'maplibre-gl'
import { PROGRAMS, tintOf } from './plates'
import type { Props } from './StoryMap'

const EMPTY: FeatureCollection = { type: 'FeatureCollection', features: [] }

/** setData on a source only when its inputs (compared by identity) differ from the last ones sent. */
function put(map: maplibregl.Map, sent: Map<string, unknown[]>, source: string, inputs: unknown[], make: () => FeatureCollection) {
  const last = sent.get(source)
  if (last && last.length === inputs.length && last.every((v, i) => v === inputs[i])) return
  sent.set(source, inputs)
  ;(map.getSource(source) as maplibregl.GeoJSONSource).setData(make())
}

export function sendData(map: maplibregl.Map, { view, groups, rail, districts }: Props, sent: Map<string, unknown[]>) {
  const vis = (ids: string[], on: boolean) => ids.forEach((id) => map.setLayoutProperty(id, 'visibility', on ? 'visible' : 'none'))
  const fc = (features: Feature[]): FeatureCollection => ({ type: 'FeatureCollection', features })
  // Each source keeps its data once sent and its layers are hidden between plates, so moving between plates never
  // makes the map re-read thousands of points.
  put(map, sent, 'pts', [groups], () => fc(groups.map((g) => ({
    type: 'Feature', geometry: { type: 'Point', coordinates: [g.lon, g.lat] },
    properties: { tint: tintOf(g.lead), m: g.budget / 1e6, n: g.projects, ...Object.fromEntries(PROGRAMS.map(({ id }) => [`m_${id}`, (g.byProgram[id] ?? 0) / 1e6])) },
  }))))
  vis(['pts'], view.kind === 'builders')
  if (view.kind !== 'builders') vis(['pts-hl'], false)
  const stations = view.kind === 'stations' ? view.stations : null
  if (stations) {
    put(map, sent, 'rail', [rail], () => rail ?? EMPTY)
    put(map, sent, 'zones', [stations], () => fc(stations.filter((s) => s.residents !== undefined).map((s) => ({ ...ring(s.lon, s.lat, 800), properties: { residents: s.residents } }))))
    put(map, sent, 'stations', [stations], () => fc(stations.map((s) => ({ type: 'Feature', properties: { label: s.place ?? '', residents: s.residents ?? null }, geometry: { type: 'Point', coordinates: [s.lon, s.lat] } }))))
  }
  vis(['rail-other', 'rail-case', 'rail-psa', 'terminals', 'terminal-labels', 'zones-fill', 'zones-edge', 'stations', 'station-labels'], !!stations)
  const fills = view.kind === 'districts' ? view.fills : null
  if (fills && districts) put(map, sent, 'districts', [fills, districts], () => ({ ...districts, features: districts.features.map((f) => ({ ...f, properties: { ...f.properties, fill: fills.get(String(f.properties?.district)) ?? null } })) }))
  vis(['district-fill', 'district-edge', 'district-hot'], !!fills)
}

/** A circle of r metres around a point, as a polygon. */
function ring(lon: number, lat: number, r: number): Feature {
  const kx = 111_320 * Math.cos((lat * Math.PI) / 180), ky = 110_574
  const c = Array.from({ length: 65 }, (_, i) => { const a = (i / 64) * 2 * Math.PI; return [lon + (r * Math.cos(a)) / kx, lat + (r * Math.sin(a)) / ky] })
  return { type: 'Feature', properties: {}, geometry: { type: 'Polygon', coordinates: [c] } }
}

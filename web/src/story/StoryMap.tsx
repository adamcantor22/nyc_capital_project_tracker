import * as maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import type { Feature, FeatureCollection } from 'geojson'
import { useEffect, useRef } from 'react'
import { PEOPLE, PROGRAMS, tintOf, type SiteGroup, type Spot } from './plates'

const BASEMAP = 'https://tiles.openfreemap.org/styles/positron'
const SHEET = '#f3f5f4'
const WATER = '#d5e2e8'
const INK = '#1d2230'
const GILT = '#f0c445'
const NYC: [[number, number], [number, number]] = [[-74.26, 40.49], [-73.69, 40.92]]
const EMPTY: FeatureCollection = { type: 'FeatureCollection', features: [] }
/** Metro-North's line colours; Penn Station Access trains run as New Haven Line service. */
const LINE_TINT: Record<string, string> = { 'Penn Station Access': '#ee0034', 'Metro-North Hudson': '#009b3a', 'Metro-North Harlem': '#0039a6', 'Metro-North New Haven': '#ee0034' }
// Radius on the square root of a point's money ($M), compressed above the median so the largest stay legible without
// covering the city. Stops (provisional design constants, set from the grouped points when written: median $4.1M,
// 90th percentile $63M, 99th $393M, 99.9th $1.9B, largest $4.5B).
const size = (field: string) => ['interpolate', ['linear'], ['sqrt', ['get', field]], 0, 1.8, 2, 3, 8, 5, 20, 9, 43, 14, 67, 16] as never

export type View =
  | { kind: 'builders'; focus: Spot | null }
  /** Only the plate's named places, framed together. */
  | { kind: 'spots'; focus: Spot | null }
  | { kind: 'districts'; fills: Map<string, string>; focus: Spot | null }
  | { kind: 'stations'; stations: { lon: number; lat: number; place: string | null; residents?: number }[]; focus: Spot | null }

interface Props {
  view: View
  /** Every point holding unfinished placed work, its projects grouped (siteGroups). */
  groups: SiteGroup[]
  /** Rail lines for the project plate (rail_lines.geojson): the project's route and Metro-North's lines. */
  rail: FeatureCollection | null
  districts: FeatureCollection | null
  spots: Spot[]
  /** Extra padding so the camera frames the part of the map the reading column does not cover. */
  padding: { top: number; right: number; bottom: number; left: number }
  /** A program whose dots stand out while the others fade (hovering its row). */
  highlight: string | null
  /** A named project whose marker is emphasised (hovering it in the list or on the map). */
  hot: string | null
  onHot: (id: string | null) => void
  /** Changes only when the camera should move: the plate, the project in focus, the layout. */
  cameraKey: string
  phone: boolean
}

const reduced = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches

/** The pinned map sheet behind the plates: one map, its layers and camera set by the current plate. */
export default function StoryMap(props: Props) {
  const { view, groups, rail, districts, spots, highlight, hot, cameraKey, phone } = props
  const box = useRef<HTMLDivElement>(null)
  const mapRef = useRef<maplibregl.Map | null>(null)
  const ready = useRef(false)
  const latest = useRef(props)
  const sent = useRef(new Map<string, unknown[]>())
  useEffect(() => {
    latest.current = props
  })

  useEffect(() => {
    const map = new maplibregl.Map({
      container: box.current!, style: BASEMAP, bounds: NYC, fitBoundsOptions: { padding: 20 },
      attributionControl: { compact: true }, maxPitch: 0, dragRotate: false,
      // On a desktop plain scrolling reads the story and Ctrl (⌘ on a Mac) + scroll zooms the map. On a phone the map
      // has its own pane, so it takes ordinary gestures.
      cooperativeGestures: !latest.current.phone,
      // A phone's 3x canvas is a common cause of browser crashes; 2x looks the same on a map.
      pixelRatio: Math.min(window.devicePixelRatio || 1, 2),
      maxTileCacheSize: 60,
    })
    map.touchZoomRotate.disableRotation()
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right')
    mapRef.current = map
    map.on('error', (e) => console.error('map:', e.error?.message ?? e))
    map.on('load', () => {
      for (const layer of map.getStyle().layers ?? []) {
        if (layer.type === 'background') map.setPaintProperty(layer.id, 'background-color', SHEET)
        else if (layer.type === 'fill' && /water/.test(layer.id)) map.setPaintProperty(layer.id, 'fill-color', WATER)
        else if (layer.type === 'fill' && /landuse|park|landcover/.test(layer.id)) map.setPaintProperty(layer.id, 'fill-opacity', 0.3)
        else if (layer.type === 'symbol' && /poi|housenumber/.test(layer.id)) map.setLayoutProperty(layer.id, 'visibility', 'none')
      }
      map.addSource('districts', { type: 'geojson', data: EMPTY })
      map.addLayer({ id: 'district-fill', type: 'fill', source: 'districts', paint: { 'fill-color': ['coalesce', ['get', 'fill'], 'rgba(0,0,0,0)'], 'fill-opacity': 0.86 } })
      map.addLayer({ id: 'district-edge', type: 'line', source: 'districts', paint: { 'line-color': 'rgba(29, 34, 48, 0.5)', 'line-width': 0.7 } })
      map.addSource('pts', { type: 'geojson', data: EMPTY })
      map.addLayer({ id: 'pts', type: 'circle', source: 'pts',
        layout: { 'circle-sort-key': ['-', 0, ['get', 'm']] },
        paint: { 'circle-color': ['get', 'tint'], 'circle-radius': size('m'), 'circle-stroke-color': '#ffffff', 'circle-stroke-width': 0.8, 'circle-opacity': 0.9 } })
      // A hovered builder's money at each point, in its tint, over the faded whole.
      map.addLayer({ id: 'pts-hl', type: 'circle', source: 'pts', layout: { visibility: 'none' },
        paint: { 'circle-radius': size('m'), 'circle-stroke-color': '#ffffff', 'circle-stroke-width': 0.8, 'circle-opacity': 0.95 } })
      map.addSource('zones', { type: 'geojson', data: EMPTY })
      map.addLayer({ id: 'zones-fill', type: 'fill', source: 'zones', paint: { 'fill-color': ['step', ['get', 'residents'], ...PEOPLE.flatMap(([v, c], i) => (i === 0 ? [c] : [v, c]))] as never, 'fill-opacity': 0.55 } })
      map.addLayer({ id: 'zones-edge', type: 'line', source: 'zones', paint: { 'line-color': INK, 'line-width': 1.2 } })
      map.addSource('rail', { type: 'geojson', data: EMPTY })
      map.addLayer({ id: 'rail-other', type: 'line', source: 'rail', filter: ['!=', ['get', 'line'], 'Penn Station Access'], layout: { 'line-cap': 'round', 'line-join': 'round' },
        paint: { 'line-color': ['match', ['get', 'line'], ...Object.entries(LINE_TINT).flat(), INK] as never, 'line-width': 2.5, 'line-opacity': 0.8 } })
      map.addLayer({ id: 'rail-case', type: 'line', source: 'rail', filter: ['==', ['get', 'line'], 'Penn Station Access'], layout: { 'line-cap': 'round', 'line-join': 'round' }, paint: { 'line-color': '#ffffff', 'line-width': 7 } })
      map.addLayer({ id: 'rail-psa', type: 'line', source: 'rail', filter: ['==', ['get', 'line'], 'Penn Station Access'], layout: { 'line-cap': 'round', 'line-join': 'round' }, paint: { 'line-color': LINE_TINT['Penn Station Access'], 'line-width': 4 } })
      map.addSource('stations', { type: 'geojson', data: EMPTY })
      map.addLayer({ id: 'stations', type: 'circle', source: 'stations',
        paint: { 'circle-radius': ['interpolate', ['linear'], ['sqrt', ['coalesce', ['get', 'residents'], 0]], 0, 8, 100, 8, 230, 13] as never, 'circle-color': '#ffffff', 'circle-stroke-color': INK, 'circle-stroke-width': 3 } })
      map.addLayer({ id: 'station-labels', type: 'symbol', source: 'stations',
        layout: { 'text-field': ['get', 'label'], 'text-font': ['Noto Sans Bold'], 'text-size': 12, 'text-offset': [0, 1.5], 'text-anchor': 'top', 'text-transform': 'uppercase', 'text-letter-spacing': 0.08 },
        paint: { 'text-color': INK, 'text-halo-color': '#ffffff', 'text-halo-width': 2 } })
      map.addSource('spots', { type: 'geojson', data: EMPTY })
      // Numbered markers for the projects a plate names: a gilt disc with its number, larger when it is the one in view.
      const on = ['boolean', ['get', 'on'], false]
      map.addLayer({ id: 'spot-disc', type: 'circle', source: 'spots',
        paint: { 'circle-radius': ['case', on, 14, 11] as never, 'circle-color': GILT, 'circle-stroke-color': INK, 'circle-stroke-width': ['case', on, 3, 2] as never } })
      map.addLayer({ id: 'spot-num', type: 'symbol', source: 'spots',
        layout: { 'text-field': ['get', 'n'], 'text-font': ['Noto Sans Bold'], 'text-size': ['case', on, 15, 13] as never, 'text-allow-overlap': true, 'text-ignore-placement': true },
        paint: { 'text-color': INK } })
      map.on('mousemove', 'spot-disc', (e) => {
        map.getCanvas().style.cursor = 'pointer'
        latest.current.onHot(String(e.features?.[0]?.properties?.id ?? '') || null)
      })
      map.on('mouseleave', 'spot-disc', () => { map.getCanvas().style.cursor = ''; latest.current.onHot(null) })
      ready.current = true
      sendData(map, latest.current, sent.current)
      moveCamera(map, latest.current, false)
      emphasise(map, latest.current)
    })
    const resize = new ResizeObserver(() => map.resize())
    resize.observe(box.current!)
    return () => { resize.disconnect(); map.remove() }
  }, [])

  // Data goes to the map only when a source's inputs change; the camera moves only when cameraKey does, so a hover,
  // a toggle or the reader's own zoom never snaps it back.
  useEffect(() => {
    if (mapRef.current && ready.current) sendData(mapRef.current, latest.current, sent.current)
  }, [view, groups, rail, districts, spots])

  useEffect(() => {
    if (mapRef.current && ready.current) moveCamera(mapRef.current, latest.current, true)
  }, [cameraKey])

  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    if (phone) map.cooperativeGestures.disable()
    else map.cooperativeGestures.enable()
  }, [phone])

  useEffect(() => {
    if (mapRef.current && ready.current) emphasise(mapRef.current, latest.current)
  }, [highlight, hot])

  return <div ref={box} className="story-map" aria-label="Map of the plate's subject" role="region" />
}

/** Hover states, set as paint without moving the camera: a program's dots over the rest, a hovered marker larger and inverted. */
function emphasise(map: maplibregl.Map, { highlight, hot }: Props) {
  map.setPaintProperty('pts', 'circle-opacity', highlight ? 0.1 : 0.9)
  map.setPaintProperty('pts', 'circle-stroke-opacity', highlight ? 0.1 : 1)
  map.setLayoutProperty('pts-hl', 'visibility', highlight ? 'visible' : 'none')
  if (highlight) {
    map.setFilter('pts-hl', ['>', ['get', `m_${highlight}`], 0])
    map.setPaintProperty('pts-hl', 'circle-radius', size(`m_${highlight}`))
    map.setPaintProperty('pts-hl', 'circle-color', tintOf(highlight))
  }
  const on = ['boolean', ['get', 'on'], false] as never
  const isHot = ['==', ['get', 'id'], hot ?? ''] as never
  map.setLayoutProperty('spot-disc', 'circle-sort-key', ['case', isHot, 2, on, 1, 0])
  map.setLayoutProperty('spot-num', 'symbol-sort-key', ['case', isHot, 2, on, 1, 0])
  map.setPaintProperty('spot-disc', 'circle-radius', ['case', isHot, 17, on, 14, 11])
  map.setPaintProperty('spot-disc', 'circle-color', ['case', isHot, INK, GILT])
  map.setPaintProperty('spot-disc', 'circle-stroke-color', ['case', isHot, GILT, INK])
  map.setPaintProperty('spot-num', 'text-color', ['case', isHot, GILT, INK])
  map.setLayoutProperty('spot-num', 'text-size', ['case', isHot, 17, on, 15, 13])
}

/** setData on a source only when its inputs (compared by identity) differ from the last ones sent. */
function put(map: maplibregl.Map, sent: Map<string, unknown[]>, source: string, inputs: unknown[], make: () => FeatureCollection) {
  const last = sent.get(source)
  if (last && last.length === inputs.length && last.every((v, i) => v === inputs[i])) return
  sent.set(source, inputs)
  ;(map.getSource(source) as maplibregl.GeoJSONSource).setData(make())
}

function sendData(map: maplibregl.Map, { view, groups, rail, districts, spots }: Props, sent: Map<string, unknown[]>) {
  const vis = (ids: string[], on: boolean) => ids.forEach((id) => map.setLayoutProperty(id, 'visibility', on ? 'visible' : 'none'))
  const fc = (features: Feature[]): FeatureCollection => ({ type: 'FeatureCollection', features })
  const builders = view.kind === 'builders'
  put(map, sent, 'pts', [builders ? groups : null], () => fc(builders ? groups.map((g) => ({
    type: 'Feature', geometry: { type: 'Point', coordinates: [g.lon, g.lat] },
    properties: { tint: tintOf(g.lead), m: g.budget / 1e6, n: g.projects, ...Object.fromEntries(PROGRAMS.map(({ id }) => [`m_${id}`, (g.byProgram[id] ?? 0) / 1e6])) },
  })) : []))
  vis(['pts'], builders)
  const stations = view.kind === 'stations' ? view.stations : null
  put(map, sent, 'rail', [stations ? rail : null], () => (stations && rail ? rail : EMPTY))
  put(map, sent, 'zones', [stations], () => fc((stations ?? []).filter((s) => s.residents !== undefined).map((s) => ({ ...ring(s.lon, s.lat, 800), properties: { residents: s.residents } }))))
  put(map, sent, 'stations', [stations], () => fc((stations ?? []).map((s) => ({ type: 'Feature', properties: { label: s.place ?? '', residents: s.residents ?? null }, geometry: { type: 'Point', coordinates: [s.lon, s.lat] } }))))
  const fills = view.kind === 'districts' ? view.fills : null
  put(map, sent, 'districts', [fills, districts], () => (fills && districts
    ? { ...districts, features: districts.features.map((f) => ({ ...f, properties: { ...f.properties, fill: fills.get(String(f.properties?.district)) ?? null } })) }
    : EMPTY))
  const focusId = view.focus?.id ?? null
  put(map, sent, 'spots', [spots, focusId], () => fc(spots.map((s, i) => ({ type: 'Feature', properties: { id: s.id, n: String(i + 1), on: focusId === s.id }, geometry: { type: 'Point', coordinates: [s.lon, s.lat] } }))))
}

function moveCamera(map: maplibregl.Map, { view, spots, padding }: Props, animate: boolean) {
  const duration = animate && !reduced() ? 1400 : 0
  const pad = (extra: number) => ({ top: padding.top + extra, bottom: padding.bottom + extra, left: padding.left + extra, right: padding.right + extra })
  const frame = (pts: { lon: number; lat: number }[], extra: number, maxZoom: number) => {
    const xs = pts.map((s) => s.lon), ys = pts.map((s) => s.lat)
    map.fitBounds([[Math.min(...xs), Math.min(...ys)], [Math.max(...xs), Math.max(...ys)]], { padding: pad(extra), maxZoom, duration })
  }
  if (view.focus) map.flyTo({ center: [view.focus.lon, view.focus.lat], zoom: 14.5, padding, duration, essential: false })
  else if (view.kind === 'spots' && spots.length) frame(spots, 50, 13)
  else if (view.kind === 'stations' && view.stations.length) frame(view.stations, 60, 13.5)
  else map.fitBounds(NYC, { padding: pad(10), duration })
}

/** A circle of r metres around a point, as a polygon. */
function ring(lon: number, lat: number, r: number): Feature {
  const kx = 111_320 * Math.cos((lat * Math.PI) / 180), ky = 110_574
  const c = Array.from({ length: 65 }, (_, i) => { const a = (i / 64) * 2 * Math.PI; return [lon + (r * Math.cos(a)) / kx, lat + (r * Math.sin(a)) / ky] })
  return { type: 'Feature', properties: {}, geometry: { type: 'Polygon', coordinates: [c] } }
}

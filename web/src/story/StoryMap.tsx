import * as maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import type { Feature, FeatureCollection } from 'geojson'
import { useEffect, useRef } from 'react'
import type { Project } from '../data/types'
import { tintOf, type Spot } from './plates'

const BASEMAP = 'https://tiles.openfreemap.org/styles/positron'
const SHEET = '#f3f5f4'
const WATER = '#d5e2e8'
const INK = '#1d2230'
const GILT = '#f0c445'
const NYC: [[number, number], [number, number]] = [[-74.26, 40.49], [-73.69, 40.92]]
const EMPTY: FeatureCollection = { type: 'FeatureCollection', features: [] }

export type View =
  | { kind: 'builders'; focus: Spot | null }
  | { kind: 'districts'; fills: Map<string, string>; focus: Spot | null }
  | { kind: 'stations'; stations: { lon: number; lat: number; place: string | null }[]; focus: Spot | null }

interface Props {
  view: View
  projects: Project[]
  districts: FeatureCollection | null
  spots: Spot[]
  /** Extra padding so the camera frames the part of the map the reading column does not cover. */
  padding: { top: number; right: number; bottom: number; left: number }
  /** A program whose dots stand out while the others fade (hovering its row). */
  highlight: string | null
  /** A named project whose marker is emphasised (hovering it in the list or on the map). */
  hot: string | null
  onHot: (id: string | null) => void
}

const reduced = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches

/** The pinned map sheet behind the plates: one map, its layers and camera set by the current plate. */
export default function StoryMap({ view, projects, districts, spots, padding, highlight, hot, onHot }: Props) {
  const box = useRef<HTMLDivElement>(null)
  const mapRef = useRef<maplibregl.Map | null>(null)
  const ready = useRef(false)
  const latest = useRef({ view, projects, districts, spots, padding, highlight, hot, onHot })
  useEffect(() => {
    latest.current = { view, projects, districts, spots, padding, highlight, hot, onHot }
  })

  useEffect(() => {
    const map = new maplibregl.Map({
      container: box.current!, style: BASEMAP, bounds: NYC, fitBoundsOptions: { padding: 20 },
      attributionControl: { compact: true }, maxPitch: 0, dragRotate: false, scrollZoom: false,
    })
    map.touchZoomRotate.disableRotation()
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
      // Radius on the square root of the budget ($M), compressed above the median so the largest projects stay
      // legible without covering the city. Stops (provisional, set from the plotted budgets when written: median
      // $0.5M, 90th percentile $25M, 99th $220M, 99.9th $2.2B, largest $6.9B) are design constants.
      const size = ['interpolate', ['linear'], ['sqrt', ['get', 'm']], 0, 1.8, 0.75, 2.6, 5, 4.5, 15, 8, 47, 14, 83, 16]
      map.addLayer({ id: 'pts', type: 'circle', source: 'pts',
        layout: { 'circle-sort-key': ['-', 0, ['get', 'm']] },
        paint: { 'circle-color': ['get', 'tint'], 'circle-radius': size as never, 'circle-stroke-color': '#ffffff', 'circle-stroke-width': 0.8, 'circle-opacity': 0.9 } })
      map.addSource('stations', { type: 'geojson', data: EMPTY })
      map.addLayer({ id: 'stations', type: 'circle', source: 'stations',
        paint: { 'circle-radius': 9, 'circle-color': '#ffffff', 'circle-stroke-color': INK, 'circle-stroke-width': 3 } })
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
      apply(map, latest.current, false)
      emphasise(map, latest.current)
    })
    return () => map.remove()
  }, [])

  useEffect(() => {
    if (mapRef.current && ready.current) apply(mapRef.current, latest.current, true)
  }, [view, projects, districts, spots, padding])

  useEffect(() => {
    if (mapRef.current && ready.current) emphasise(mapRef.current, latest.current)
  }, [highlight, hot])

  return <div ref={box} className="story-map" aria-label="Map of the plate's subject" role="region" />
}

/** Hover states, set as paint without moving the camera: a program's dots over the rest, a hovered marker larger and inverted. */
function emphasise(map: maplibregl.Map, { highlight, hot }: Props) {
  map.setPaintProperty('pts', 'circle-opacity', highlight ? ['case', ['==', ['get', 'program'], highlight], 0.95, 0.1] as never : 0.9)
  map.setPaintProperty('pts', 'circle-stroke-opacity', highlight ? ['case', ['==', ['get', 'program'], highlight], 1, 0.1] as never : 1)
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

function apply(map: maplibregl.Map, { view, projects, districts, spots, padding }: Props, animate: boolean) {
  const vis = (ids: string[], on: boolean) => ids.forEach((id) => map.setLayoutProperty(id, 'visibility', on ? 'visible' : 'none'))
  const pts: Feature[] = view.kind === 'builders'
    ? projects.filter((p) => p.status === 'current' && p.onMap && p.lon !== null && (p.tier === 'A' || p.tier === 'B')).map((p) => ({
        type: 'Feature', properties: { program: p.program, tint: tintOf(p.program), m: p.budget / 1e6 }, geometry: { type: 'Point', coordinates: [p.lon!, p.lat!] } }))
    : []
  ;(map.getSource('pts') as maplibregl.GeoJSONSource).setData({ type: 'FeatureCollection', features: pts })
  vis(['pts'], view.kind === 'builders')

  const fc = view.kind === 'districts' && districts
    ? { ...districts, features: districts.features.map((f) => ({ ...f, properties: { ...f.properties, fill: view.fills.get(String(f.properties?.district)) ?? null } })) }
    : EMPTY
  ;(map.getSource('districts') as maplibregl.GeoJSONSource).setData(fc)

  const st: Feature[] = view.kind === 'stations' ? view.stations.map((s) => ({ type: 'Feature', properties: { label: s.place ?? '' }, geometry: { type: 'Point', coordinates: [s.lon, s.lat] } })) : []
  ;(map.getSource('stations') as maplibregl.GeoJSONSource).setData({ type: 'FeatureCollection', features: st })

  const sp: Feature[] = spots.map((s, i) => ({ type: 'Feature', properties: { id: s.id, n: String(i + 1), on: view.focus?.id === s.id }, geometry: { type: 'Point', coordinates: [s.lon, s.lat] } }))
  ;(map.getSource('spots') as maplibregl.GeoJSONSource).setData({ type: 'FeatureCollection', features: sp })

  const duration = animate && !reduced() ? 1400 : 0
  if (view.focus) {
    map.flyTo({ center: [view.focus.lon, view.focus.lat], zoom: 14.5, padding, duration, essential: false })
  } else if (view.kind === 'stations' && view.stations.length) {
    const xs = view.stations.map((s) => s.lon), ys = view.stations.map((s) => s.lat)
    map.fitBounds([[Math.min(...xs), Math.min(...ys)], [Math.max(...xs), Math.max(...ys)]], { padding: { ...padding, top: padding.top + 80, bottom: padding.bottom + 80, left: padding.left + 80, right: padding.right + 80 }, maxZoom: 13.5, duration })
  } else {
    map.fitBounds(NYC, { padding: { ...padding, top: padding.top + 10, bottom: padding.bottom + 10 }, duration })
  }
}

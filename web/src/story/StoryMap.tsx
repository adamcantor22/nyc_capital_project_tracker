import * as maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import type { Feature, FeatureCollection } from 'geojson'
import { useEffect, useRef } from 'react'
import type { Project } from '../data/types'
import { hatchedDisc } from '../map/patterns'
import { PROGRAMS, tintOf, type Spot } from './plates'

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
}

const reduced = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches

/** The pinned map sheet behind the plates: one map, its layers and camera set by the current plate. */
export default function StoryMap({ view, projects, districts, spots, padding }: Props) {
  const box = useRef<HTMLDivElement>(null)
  const mapRef = useRef<maplibregl.Map | null>(null)
  const ready = useRef(false)
  const latest = useRef({ view, projects, districts, spots, padding })
  useEffect(() => {
    latest.current = { view, projects, districts, spots, padding }
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
      for (const { tint } of PROGRAMS) map.addImage(`b-${tint}`, hatchedDisc(tint), { pixelRatio: 2 })
      map.addSource('districts', { type: 'geojson', data: EMPTY })
      map.addLayer({ id: 'district-fill', type: 'fill', source: 'districts', paint: { 'fill-color': ['coalesce', ['get', 'fill'], 'rgba(0,0,0,0)'], 'fill-opacity': 0.86 } })
      map.addLayer({ id: 'district-edge', type: 'line', source: 'districts', paint: { 'line-color': 'rgba(29, 34, 48, 0.5)', 'line-width': 0.7 } })
      map.addSource('pts', { type: 'geojson', data: EMPTY })
      const size = ['interpolate', ['linear'], ['sqrt', ['get', 'b']], 300, 2.5, 3000, 4, 30000, 11, 70000, 18]
      map.addLayer({ id: 'pts-a', type: 'circle', source: 'pts', filter: ['==', ['get', 'tier'], 'A'],
        paint: { 'circle-color': ['get', 'tint'], 'circle-radius': size as never, 'circle-stroke-color': INK, 'circle-stroke-width': 0.6, 'circle-opacity': 0.92 } })
      map.addLayer({ id: 'pts-b', type: 'symbol', source: 'pts', filter: ['==', ['get', 'tier'], 'B'],
        layout: { 'icon-image': ['concat', 'b-', ['get', 'tint']], 'icon-size': ['/', size as never, 9.5], 'icon-allow-overlap': true } })
      map.addSource('stations', { type: 'geojson', data: EMPTY })
      map.addLayer({ id: 'stations', type: 'circle', source: 'stations',
        paint: { 'circle-radius': 9, 'circle-color': '#ffffff', 'circle-stroke-color': INK, 'circle-stroke-width': 3 } })
      map.addLayer({ id: 'station-labels', type: 'symbol', source: 'stations',
        layout: { 'text-field': ['get', 'label'], 'text-font': ['Noto Sans Bold'], 'text-size': 12, 'text-offset': [0, 1.5], 'text-anchor': 'top', 'text-transform': 'uppercase', 'text-letter-spacing': 0.08 },
        paint: { 'text-color': INK, 'text-halo-color': '#ffffff', 'text-halo-width': 2 } })
      map.addSource('spots', { type: 'geojson', data: EMPTY })
      map.addLayer({ id: 'spot-ring', type: 'circle', source: 'spots',
        paint: { 'circle-radius': ['case', ['boolean', ['get', 'on'], false], 17, 12], 'circle-color': 'rgba(0,0,0,0)', 'circle-stroke-color': ['case', ['boolean', ['get', 'on'], false], GILT, INK], 'circle-stroke-width': ['case', ['boolean', ['get', 'on'], false], 4, 2] } })
      map.addLayer({ id: 'spot-num', type: 'symbol', source: 'spots',
        layout: { 'text-field': ['get', 'n'], 'text-font': ['Noto Sans Bold'], 'text-size': 13, 'text-offset': [1.35, -1.35], 'text-allow-overlap': true },
        paint: { 'text-color': INK, 'text-halo-color': GILT, 'text-halo-width': 3 } })
      ready.current = true
      apply(map, latest.current, false)
    })
    return () => map.remove()
  }, [])

  useEffect(() => {
    if (mapRef.current && ready.current) apply(mapRef.current, latest.current, true)
  }, [view, projects, districts, spots, padding])

  return <div ref={box} className="story-map" aria-label="Map of the plate's subject" role="region" />
}

function apply(map: maplibregl.Map, { view, projects, districts, spots, padding }: Props, animate: boolean) {
  const vis = (ids: string[], on: boolean) => ids.forEach((id) => map.setLayoutProperty(id, 'visibility', on ? 'visible' : 'none'))
  const pts: Feature[] = view.kind === 'builders'
    ? projects.filter((p) => p.status === 'current' && p.onMap && p.lon !== null && (p.tier === 'A' || p.tier === 'B')).map((p) => ({
        type: 'Feature', properties: { tier: p.tier, tint: tintOf(p.program), b: p.budget / 1e3 }, geometry: { type: 'Point', coordinates: [p.lon!, p.lat!] } }))
    : []
  ;(map.getSource('pts') as maplibregl.GeoJSONSource).setData({ type: 'FeatureCollection', features: pts })
  vis(['pts-a', 'pts-b'], view.kind === 'builders')

  const fc = view.kind === 'districts' && districts
    ? { ...districts, features: districts.features.map((f) => ({ ...f, properties: { ...f.properties, fill: view.fills.get(String(f.properties?.district)) ?? null } })) }
    : EMPTY
  ;(map.getSource('districts') as maplibregl.GeoJSONSource).setData(fc)

  const st: Feature[] = view.kind === 'stations' ? view.stations.map((s) => ({ type: 'Feature', properties: { label: s.place ?? '' }, geometry: { type: 'Point', coordinates: [s.lon, s.lat] } })) : []
  ;(map.getSource('stations') as maplibregl.GeoJSONSource).setData({ type: 'FeatureCollection', features: st })

  const sp: Feature[] = spots.map((s, i) => ({ type: 'Feature', properties: { n: String(i + 1), on: view.focus?.id === s.id }, geometry: { type: 'Point', coordinates: [s.lon, s.lat] } }))
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

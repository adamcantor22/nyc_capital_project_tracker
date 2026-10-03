import type { FeatureCollection } from 'geojson'
import * as maplibregl from 'maplibre-gl'
import type { GeoJSONSource, Map as MlMap } from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { useEffect, useRef } from 'react'
import type { Areas } from '../data/load'
import type { Project } from '../data/types'
import { money } from '../measures/registry'
import { addPatterns } from './patterns'
import { OTHER_COLOR, THEME_SLOTS, themeColor } from './themes'

type FC = FeatureCollection

const BASEMAP = 'https://tiles.openfreemap.org/styles/positron'
const SHEET = '#f3f5f4'
const WATER = '#d5e2e8'
const INK = '#1d2230'
const NYC: [[number, number], [number, number]] = [[-74.26, 40.49], [-73.69, 40.92]]

export interface Bounds { w: number; s: number; e: number; n: number }
/** mark: 'address' drops an ink pin, 'me' the visitor's location dot; neither looks like a project disc. */
export interface Focus { lon: number; lat: number; zoom: number; key: number; mark: 'address' | 'me' | null }

interface Props {
  projects: Project[]
  areas: Areas | null
  focus: Focus | null
  highlightTheme: string | null
  highlightTier: string | null
  /** Coarse tiers the visitor asked for (precision key selected): their washes show at every zoom. */
  shownTiers: string[]
  selectedId: string | null
  onSelect(id: string | null): void
  onView(b: Bounds): void
}

const colorExpr = ['match', ['get', 'theme'], ...THEME_SLOTS.flatMap((s) => [s.theme, s.color]), OTHER_COLOR]

function points(projects: Project[]): FC {
  return {
    type: 'FeatureCollection',
    features: projects.filter((p) => p.onMap && p.lon !== null).map((p) => ({
      type: 'Feature',
      id: undefined,
      properties: { id: p.id, theme: p.theme, tier: p.tier, b: p.budget, color: themeColor(p.theme), title: p.title },
      geometry: { type: 'Point', coordinates: [p.lon!, p.lat!] },
    })),
  }
}

/** Coarse projects never become pins: they are counted onto the area they are known to. */
function washes(projects: Project[], areas: Record<string, FC>): Record<string, FC> {
  const agg = (key: (p: Project) => string | null, tier: string) => {
    const m = new Map<string, { n: number; b: number }>()
    for (const p of projects) {
      if (p.tier !== tier) continue
      const k = key(p)
      if (!k) continue
      const a = m.get(k) ?? { n: 0, b: 0 }
      a.n += 1
      a.b += p.budget
      m.set(k, a)
    }
    return m
  }
  const out: Record<string, FC> = {}
  const spec: [string, string, string, (p: Project) => string | null][] = [
    ['C', 'neighborhoods', 'name', (p) => p.neighborhood ?? p.matchedTo],
    ['D', 'districts', 'district', (p) => (p.district ?? p.districts[0])?.toString() ?? null],
    ['E', 'boroughs', 'borough', (p) => p.borough],
  ]
  for (const [tier, layer, prop, key] of spec) {
    const m = agg(key, tier)
    const max = Math.max(1, ...[...m.values()].map((v) => v.b))
    out[tier] = {
      type: 'FeatureCollection',
      features: (areas[layer]?.features ?? []).flatMap((f): FC['features'] => {
        const a = m.get(String(f.properties?.[prop]))
        return a ? [{ ...f, properties: { ...f.properties, n: a.n, b: a.b, w: Math.sqrt(a.b / max), tier } }] : []
      }),
    }
  }
  return out
}

export default function MapView({ projects, areas: areaData, focus, highlightTheme, highlightTier, shownTiers, selectedId, onSelect, onView }: Props) {
  const box = useRef<HTMLDivElement>(null)
  const mapRef = useRef<MlMap | null>(null)
  const areas = useRef<Record<string, FC>>({})
  const marker = useRef<maplibregl.Marker | null>(null)
  const ready = useRef(false)
  const latest = useRef({ projects, onSelect, onView })
  useEffect(() => {
    latest.current = { projects, onSelect, onView }
  })

  useEffect(() => {
    const map = new maplibregl.Map({
      container: box.current!,
      style: BASEMAP,
      bounds: NYC,
      fitBoundsOptions: { padding: 20 },
      attributionControl: { compact: true },
      maxPitch: 0,
      dragRotate: false,
    })
    map.touchZoomRotate.disableRotation()
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'bottom-right')
    mapRef.current = map
    const popup = new maplibregl.Popup({ closeButton: false, closeOnClick: false, offset: 10, className: 'atlas-tip' })

    map.on('load', () => {
      for (const layer of map.getStyle().layers ?? []) {
        if (layer.type === 'background') map.setPaintProperty(layer.id, 'background-color', SHEET)
        else if (layer.type === 'fill' && /water/.test(layer.id)) map.setPaintProperty(layer.id, 'fill-color', WATER)
        else if (layer.type === 'fill' && /landuse|park|landcover/.test(layer.id)) map.setPaintProperty(layer.id, 'fill-opacity', 0.35)
      }
      addPatterns(map)
      const empty: FC = { type: 'FeatureCollection', features: [] }
      for (const tier of ['E', 'D', 'C']) {
        map.addSource(`wash-${tier}`, { type: 'geojson', data: empty })
        map.addLayer({
          id: `wash-${tier}`, type: 'fill', source: `wash-${tier}`,
          paint: { 'fill-pattern': `wash-${tier}`, 'fill-opacity': washOpacity(false) as never },
        })
        map.addLayer({
          id: `wash-${tier}-edge`, type: 'line', source: `wash-${tier}`,
          paint: { 'line-color': INK, 'line-opacity': edgeOpacity(false) as never, 'line-width': 0.6, 'line-dasharray': [3, 2] },
        })
      }
      map.addSource('pts', { type: 'geojson', data: empty })
      const size = ['interpolate', ['linear'], ['sqrt', ['get', 'b']], 300, 3, 3000, 5, 30000, 15, 70000, 22]
      map.addLayer({
        id: 'pts-a', type: 'circle', source: 'pts', filter: ['==', ['get', 'tier'], 'A'],
        paint: {
          'circle-color': colorExpr as never,
          'circle-radius': size as never,
          'circle-stroke-color': INK, 'circle-stroke-width': 0.8,
        },
      })
      map.addLayer({
        id: 'pts-b', type: 'symbol', source: 'pts', filter: ['==', ['get', 'tier'], 'B'],
        layout: {
          'icon-image': ['concat', 'b-', ['get', 'color']],
          'icon-size': ['/', size as never, 9.5],
          'icon-allow-overlap': true,
        },
      })
      map.addLayer({
        id: 'pts-sel', type: 'circle', source: 'pts', filter: ['==', ['get', 'id'], ''],
        paint: { 'circle-radius': ['+', size as never, 5] as never, 'circle-color': 'rgba(0,0,0,0)', 'circle-stroke-color': INK, 'circle-stroke-width': 2.5 },
      })
      ready.current = true
      sync()
      emitView()
    })

    function sync() {
      if (!ready.current) return
      const ps = latest.current.projects
      ;(map.getSource('pts') as GeoJSONSource).setData(points(ps))
      const w = washes(ps, areas.current)
      for (const t of ['C', 'D', 'E']) (map.getSource(`wash-${t}`) as GeoJSONSource).setData(w[t])
    }
    function emitView() {
      const b = map.getBounds()
      latest.current.onView({ w: b.getWest(), s: b.getSouth(), e: b.getEast(), n: b.getNorth() })
    }
    ;(map as unknown as { __sync: () => void }).__sync = sync
    map.on('moveend', emitView)

    for (const id of ['pts-a', 'pts-b']) {
      map.on('mouseenter', id, () => (map.getCanvas().style.cursor = 'pointer'))
      map.on('mouseleave', id, () => {
        map.getCanvas().style.cursor = ''
        popup.remove()
      })
      map.on('mousemove', id, (e: maplibregl.MapLayerMouseEvent) => {
        const f = e.features?.[0]
        if (!f) return
        const p = f.properties as { title: string; b: number; tier: string }
        popup.setLngLat(e.lngLat).setHTML(
          `<strong>${escapeHtml(p.title)}</strong><span>${money(p.b)}${p.tier === 'B' ? ' · location approximate' : ''}</span>`,
        ).addTo(map)
      })
      map.on('click', id, (e: maplibregl.MapLayerMouseEvent) => {
        const f = e.features?.[0]
        if (f) latest.current.onSelect(String(f.properties?.id))
      })
    }
    for (const t of ['C', 'D', 'E']) {
      map.on('mousemove', `wash-${t}`, (e: maplibregl.MapLayerMouseEvent) => {
        if (map.queryRenderedFeatures(e.point, { layers: ['pts-a', 'pts-b'] }).length) return
        const f = e.features?.[0]
        if (!f) return
        const { n, b, name, district, borough } = f.properties as Record<string, string | number>
        const where = name ?? (district ? `Community district ${district}` : borough)
        popup.setLngLat(e.lngLat).setHTML(
          `<strong>${escapeHtml(String(where))}</strong><span>${n} project${n === 1 ? '' : 's'} (${money(Number(b))}) known only to this ${t === 'C' ? 'neighborhood' : t === 'D' ? 'district' : 'borough'}</span>`,
        ).addTo(map)
      })
      map.on('mouseleave', `wash-${t}`, () => popup.remove())
    }
    map.on('click', (e: maplibregl.MapMouseEvent) => {
      if (!map.queryRenderedFeatures(e.point, { layers: ['pts-a', 'pts-b'] }).length) latest.current.onSelect(null)
    })
    return () => map.remove()
  }, [])

  useEffect(() => {
    if (areaData) areas.current = areaData
    ;(mapRef.current as unknown as { __sync?: () => void } | null)?.__sync?.()
  }, [projects, areaData])

  useEffect(() => {
    const map = mapRef.current
    if (!map || !focus) return
    map.flyTo({ center: [focus.lon, focus.lat], zoom: Math.max(map.getZoom(), focus.zoom), duration: 900, essential: false })
    marker.current?.remove()
    if (focus.mark) {
      const el = document.createElement('div')
      el.className = focus.mark === 'me' ? 'me-dot' : 'address-pin'
      el.setAttribute('aria-label', focus.mark === 'me' ? 'Your location' : 'Searched address')
      if (focus.mark === 'address') {
        el.innerHTML = '<svg viewBox="0 0 24 32" width="24" height="32" aria-hidden="true"><path d="M12 1C6 1 1.5 5.4 1.5 11.2 1.5 19 12 31 12 31s10.5-12 10.5-19.8C22.5 5.4 18 1 12 1z" fill="#1d2230" stroke="#fff" stroke-width="1.5"/><circle cx="12" cy="11" r="4" fill="#fff"/></svg>'
      }
      marker.current = new maplibregl.Marker({ element: el, anchor: focus.mark === 'me' ? 'center' : 'bottom' })
        .setLngLat([focus.lon, focus.lat]).addTo(map)
    }
  }, [focus])

  useEffect(() => {
    const map = mapRef.current
    if (!map || !ready.current) return
    map.setFilter('pts-sel', ['==', ['get', 'id'], selectedId ?? ''])
  }, [selectedId])

  useEffect(() => {
    const map = mapRef.current
    if (!map || !ready.current) return
    const dim = (on: unknown[]) => (highlightTheme || highlightTier ? ['case', on, 1, 0.12] : 1)
    const on = ['all', highlightTheme ? themeKey(highlightTheme) : true, highlightTier ? ['==', ['get', 'tier'], highlightTier] : true]
    map.setPaintProperty('pts-a', 'circle-opacity', dim(on) as never)
    map.setPaintProperty('pts-a', 'circle-stroke-opacity', dim(on) as never)
    map.setPaintProperty('pts-b', 'icon-opacity', dim(on) as never)
    for (const t of ['C', 'D', 'E']) {
      const asked = highlightTier === t || shownTiers.includes(t)
      const dimmed = highlightTier !== null && highlightTier !== t
      map.setPaintProperty(`wash-${t}`, 'fill-opacity', dimmed ? 0 : (washOpacity(asked) as never))
      map.setPaintProperty(`wash-${t}-edge`, 'line-opacity', dimmed ? 0 : (edgeOpacity(asked) as never))
    }
  }, [highlightTheme, highlightTier, shownTiers])

  return <div ref={box} className="map" role="region" aria-label="Map of capital projects" />
}

/** Coarse washes are off until the visitor hovers or selects that precision key. */
function washOpacity(asked: boolean) {
  const byBudget = (lo: number, hi: number) => ['interpolate', ['linear'], ['get', 'w'], 0, lo, 1, hi]
  return asked ? byBudget(0.3, 0.8) : 0
}
function edgeOpacity(asked: boolean) {
  return asked ? 0.45 : 0
}

/** Expression: does this feature belong to the highlighted legend entry? "Other" covers the four small themes. */
function themeKey(theme: string) {
  if (theme === '__other') return ['!', ['in', ['get', 'theme'], ['literal', THEME_SLOTS.map((s) => s.theme)]]]
  return ['==', ['get', 'theme'], theme]
}

function escapeHtml(s: string) {
  return s.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]!)
}

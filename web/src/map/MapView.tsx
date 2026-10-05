import type { FeatureCollection } from 'geojson'
import * as maplibregl from 'maplibre-gl'
import type { GeoJSONSource, Map as MlMap } from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import { useEffect, useRef, useState } from 'react'
import type { Box } from '../measures/aggregate'
import type { Project } from '../data/types'
import type { Site } from '../areas/aggregate'
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
export interface Focus { lon: number; lat: number; zoom: number; key: number; mark: 'address' | 'me' | null; bounds?: Bounds }

interface Props {
  projects: Project[]
  /** Per-site points and budget shares; until loaded, each project is drawn at its single point. */
  sites: Map<string, Site[]> | null
  focus: Focus | null
  highlightTheme: string | null
  highlightTier: string | null
  /** Area view: polygons of one level, each feature carrying key, color, label and labelPoint. */
  areaLayer: { level: string; fc: FC; labels: FC } | null
  selectedArea: string | null
  onAreaClick(key: string | null): void
  selectedId: string | null
  onSelect(id: string | null): void
  /** Box-select mode (also Shift-drag on desktop): the drawn box is reported through onArea. */
  selecting: boolean
  area: Box | null
  onArea(b: Box | null): void
  onView(b: Bounds): void
}

const colorExpr = ['match', ['get', 'theme'], ...THEME_SLOTS.flatMap((s) => [s.theme, s.color]), OTHER_COLOR]

/** One mark per site: a multi-site project (ten bridges, four pools) is drawn at each, sized by its share. */
function points(projects: Project[], sites: Map<string, Site[]> | null): FC {
  return {
    type: 'FeatureCollection',
    features: projects.filter((p) => p.onMap && p.lon !== null).flatMap((p) => {
      const props = { id: p.id, theme: p.theme, tier: p.tier, color: themeColor(p.theme), title: p.title, total: p.budget }
      const ss = sites?.get(p.id)
      const at = ss && ss.length > 1 ? ss.map((s) => ({ lon: s.lon, lat: s.lat, share: s.share })) : [{ lon: p.lon!, lat: p.lat!, share: 1 }]
      return at.map((s) => ({
        type: 'Feature' as const,
        properties: { ...props, b: p.budget * s.share, n: at.length },
        geometry: { type: 'Point' as const, coordinates: [s.lon, s.lat] },
      }))
    }),
  }
}

export default function MapView({ projects, sites, focus, highlightTheme, highlightTier, areaLayer, selectedArea, onAreaClick, selectedId, onSelect, onView, selecting, area, onArea }: Props) {
  const box = useRef<HTMLDivElement>(null)
  const mapRef = useRef<MlMap | null>(null)
  const marker = useRef<maplibregl.Marker | null>(null)
  const ready = useRef(false)
  // State as well as the ref, so effects that ran before the style loaded (state from the URL) run again.
  const [loaded, setLoaded] = useState(false)
  const areaOn = !!areaLayer
  const latest = useRef({ projects, sites, onSelect, onView, onArea, selecting, onAreaClick, areaOn: false })
  useEffect(() => {
    latest.current = { projects, sites, onSelect, onView, onArea, selecting, onAreaClick, areaOn: !!areaLayer }
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
    map.boxZoom.disable()
    enableBoxSelect(map, () => latest.current.selecting, (b) => latest.current.onArea(b))
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
      map.addSource('areas', { type: 'geojson', data: empty })
      map.addSource('area-labels', { type: 'geojson', data: empty })
      map.addLayer({ id: 'areas-fill', type: 'fill', source: 'areas', paint: { 'fill-color': ['get', 'color'], 'fill-opacity': 0.82 } })
      map.addLayer({
        id: 'areas-edge', type: 'line', source: 'areas',
        paint: {
          'line-color': ['case', ['boolean', ['get', 'selected'], false], INK, 'rgba(29, 34, 48, 0.55)'],
          'line-width': ['case', ['boolean', ['get', 'selected'], false], 2.5, ['get', 'edge']],
        },
      })
      map.addSource('area', { type: 'geojson', data: empty })
      map.addLayer({ id: 'area-fill', type: 'fill', source: 'area', paint: { 'fill-color': '#f0c445', 'fill-opacity': 0.12 } })
      map.addLayer({ id: 'area-edge', type: 'line', source: 'area', paint: { 'line-color': INK, 'line-width': 1.5, 'line-dasharray': [4, 2] } })
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
      map.addLayer({
        id: 'area-labels', type: 'symbol', source: 'area-labels',
        layout: {
          'text-field': ['get', 'label'], 'text-font': ['Noto Sans Bold'], 'text-size': 11,
          'text-allow-overlap': false, 'text-padding': 2,
        },
        paint: { 'text-color': INK, 'text-halo-color': '#ffffff', 'text-halo-width': 1.4 },
      })
      ready.current = true
      setLoaded(true)
      sync()
      emitView()
    })

    function sync() {
      if (!ready.current) return
      ;(map.getSource('pts') as GeoJSONSource).setData(points(latest.current.projects, latest.current.sites))
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
        const p = f.properties as { title: string; b: number; total: number; n: number; tier: string }
        const amount = p.n > 1 ? `One of ${p.n} sites · about ${money(p.b)} of ${money(p.total)}` : money(p.b)
        popup.setLngLat(e.lngLat).setHTML(
          `<strong>${escapeHtml(p.title)}</strong><span>${amount}${p.tier === 'B' ? ' · location approximate' : ''}</span>`,
        ).addTo(map)
      })
      map.on('click', id, (e: maplibregl.MapLayerMouseEvent) => {
        const f = e.features?.[0]
        if (f) latest.current.onSelect(String(f.properties?.id))
      })
    }
    map.on('mousemove', 'areas-fill', (e: maplibregl.MapLayerMouseEvent) => {
      if (map.queryRenderedFeatures(e.point, { layers: ['pts-a', 'pts-b'] }).length) return
      const f = e.features?.[0]
      if (!f) return
      map.getCanvas().style.cursor = 'pointer'
      const { name, value } = f.properties as Record<string, string>
      popup.setLngLat(e.lngLat).setHTML(`<strong>${escapeHtml(name)}</strong><span>${escapeHtml(value)}</span>`).addTo(map)
    })
    map.on('mouseleave', 'areas-fill', () => {
      map.getCanvas().style.cursor = ''
      popup.remove()
    })
    map.on('click', 'areas-fill', (e: maplibregl.MapLayerMouseEvent) => {
      if (map.queryRenderedFeatures(e.point, { layers: ['pts-a', 'pts-b'] }).length) return
      const f = e.features?.[0]
      if (f) latest.current.onAreaClick(String(f.properties?.key))
    })
    map.on('click', (e: maplibregl.MapMouseEvent) => {
      const hit = map.queryRenderedFeatures(e.point, { layers: ['pts-a', 'pts-b', ...(latest.current.areaOn ? ['areas-fill'] : [])] })
      if (!hit.length) {
        latest.current.onSelect(null)
        if (latest.current.areaOn) latest.current.onAreaClick(null)
      }
    })
    return () => map.remove()
  }, [])

  useEffect(() => {
    const map = mapRef.current
    if (!map || !ready.current) return
    const empty: FC = { type: 'FeatureCollection', features: [] }
    const fc = areaLayer ? { ...areaLayer.fc, features: areaLayer.fc.features.map((f) => ({ ...f, properties: { ...f.properties, selected: f.properties?.key === selectedArea } })) } : empty
    ;(map.getSource('areas') as GeoJSONSource).setData(fc)
    ;(map.getSource('area-labels') as GeoJSONSource).setData(areaLayer?.labels ?? empty)
  }, [areaLayer, selectedArea, loaded])

  useEffect(() => {
    if (!areaLayer?.level) return
    mapRef.current?.fitBounds(NYC, { padding: 30, duration: 700 })
  }, [areaLayer?.level])

  useEffect(() => {
    ;(mapRef.current as unknown as { __sync?: () => void } | null)?.__sync?.()
  }, [projects, sites])

  useEffect(() => {
    const map = mapRef.current
    if (!map || !focus) return
    // Leave room for the panel that opens with it: right side on desktop, bottom sheet on phones.
    const phone = map.getContainer().clientWidth < 760
    const padding = phone ? { top: 100, left: 20, right: 20, bottom: map.getContainer().clientHeight * 0.55 } : { top: 70, left: 30, bottom: 30, right: 470 }
    if (focus.bounds) {
      const b = focus.bounds
      map.fitBounds([[b.w, b.s], [b.e, b.n]], { padding, maxZoom: 15, duration: 900 })
      marker.current?.remove()
      return
    }
    map.flyTo({ center: [focus.lon, focus.lat], zoom: Math.max(map.getZoom(), focus.zoom), duration: 900, essential: false,
      // offset, not padding: padding passed to flyTo stays on the map afterwards.
      offset: focus.mark ? [0, 0] : [(padding.left - padding.right) / 2, (padding.top - padding.bottom) / 2] })
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
    const src = map.getSource('area') as GeoJSONSource | undefined
    src?.setData({
      type: 'FeatureCollection',
      features: area ? [{ type: 'Feature', properties: {}, geometry: { type: 'Polygon', coordinates: [[[area.w, area.s], [area.e, area.s], [area.e, area.n], [area.w, area.n], [area.w, area.s]]] } }] : [],
    })
  }, [area, loaded])

  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    map.getCanvas().classList.toggle('selecting', selecting)
    // On touch, a drag must draw the box rather than pan the map.
    if (selecting) {
      map.dragPan.disable()
      map.touchZoomRotate.disable()
    } else {
      map.dragPan.enable()
      map.touchZoomRotate.enable()
      map.touchZoomRotate.disableRotation()
    }
  }, [selecting])

  useEffect(() => {
    const map = mapRef.current
    if (!map || !ready.current) return
    const sel = ['==', ['get', 'id'], selectedId ?? '']
    map.setFilter('pts-sel', sel as never)
    // Area view shows areas, not projects: only a project opened from a list or panel keeps its pin.
    const only = (tier: string) => (areaOn ? ['all', ['==', ['get', 'tier'], tier], sel] : ['==', ['get', 'tier'], tier])
    map.setFilter('pts-a', only('A') as never)
    map.setFilter('pts-b', only('B') as never)
  }, [selectedId, areaOn, loaded])

  useEffect(() => {
    const map = mapRef.current
    if (!map || !ready.current) return
    const dim = (on: unknown[]) => (highlightTheme || highlightTier ? ['case', on, 1, 0.12] : 1)
    const on = ['all', highlightTheme ? themeKey(highlightTheme) : true, highlightTier ? ['==', ['get', 'tier'], highlightTier] : true]
    map.setPaintProperty('pts-a', 'circle-opacity', dim(on) as never)
    map.setPaintProperty('pts-a', 'circle-stroke-opacity', dim(on) as never)
    map.setPaintProperty('pts-b', 'icon-opacity', dim(on) as never)
  }, [highlightTheme, highlightTier, loaded])

  return <div ref={box} className="map" role="region" aria-label="Map of capital projects" />
}

/** Drag a rectangle in select mode, or Shift-drag at any time, to report a lon/lat box. */
function enableBoxSelect(map: MlMap, selecting: () => boolean, done: (b: Box) => void) {
  const host = map.getCanvasContainer()
  let start: { x: number; y: number } | null = null
  let box: HTMLDivElement | null = null
  const local = (e: PointerEvent) => {
    const r = host.getBoundingClientRect()
    return { x: e.clientX - r.left, y: e.clientY - r.top }
  }
  host.addEventListener('pointerdown', (e) => {
    if (!(selecting() || e.shiftKey) || e.button !== 0) return
    e.preventDefault()
    e.stopPropagation()
    map.dragPan.disable()
    host.setPointerCapture(e.pointerId)
    start = local(e)
    box = document.createElement('div')
    box.className = 'select-box'
    host.appendChild(box)
  }, true)
  host.addEventListener('pointermove', (e) => {
    if (!start || !box) return
    const p = local(e)
    Object.assign(box.style, {
      left: `${Math.min(p.x, start.x)}px`, top: `${Math.min(p.y, start.y)}px`,
      width: `${Math.abs(p.x - start.x)}px`, height: `${Math.abs(p.y - start.y)}px`,
    })
  })
  const end = (e: PointerEvent) => {
    if (!start) return
    const p = local(e)
    box?.remove()
    box = null
    map.dragPan.enable()
    const s = start
    start = null
    if (Math.abs(p.x - s.x) < 8 || Math.abs(p.y - s.y) < 8) return
    const a = map.unproject([s.x, s.y])
    const b = map.unproject([p.x, p.y])
    done({ w: Math.min(a.lng, b.lng), e: Math.max(a.lng, b.lng), s: Math.min(a.lat, b.lat), n: Math.max(a.lat, b.lat) })
  }
  host.addEventListener('pointerup', end)
  host.addEventListener('pointercancel', end)
}

/** Expression: does this feature belong to the highlighted legend entry? "Other" covers the four small themes. */
function themeKey(theme: string) {
  if (theme === '__other') return ['!', ['in', ['get', 'theme'], ['literal', THEME_SLOTS.map((s) => s.theme)]]]
  return ['==', ['get', 'theme'], theme]
}

function escapeHtml(s: string) {
  return s.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]!)
}

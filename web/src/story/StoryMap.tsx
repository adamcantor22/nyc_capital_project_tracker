import * as maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import type { FeatureCollection } from 'geojson'
import { useEffect, useRef, useState } from 'react'
import { sendData } from './mapData'
import { PEOPLE, tintOf, type SiteGroup, type Spot } from './plates'

const BASEMAP = 'https://tiles.openfreemap.org/styles/positron'
const SHEET = '#f3f5f4'
const WATER = '#d5e2e8'
const INK = '#1d2230'
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
  | { kind: 'stations'; stations: { lon: number; lat: number; place: string | null; residents?: number }[]; focus: Spot | null
      /** Other points the camera frames with the stations (the Manhattan terminals). */
      extent?: { lon: number; lat: number }[] }

export interface Props {
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
  /** A district outlined on the map (hovering its line in the rank chart). */
  hotArea?: string | null
  /** A named project chosen on the map (its marker tapped or clicked). */
  onPick: (s: Spot) => void
  /** Changes only when the camera should move: the plate, the project in focus, the layout. */
  cameraKey: string
  phone: boolean
}

const HINT_KEY = 'story-zoom-hint'
const reduced = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches

/** The pinned map sheet behind the plates: one map, its layers and camera set by the current plate. */
export default function StoryMap(props: Props) {
  const { view, groups, rail, districts, spots, highlight, hot, cameraKey } = props
  const box = useRef<HTMLDivElement>(null)
  const mapRef = useRef<maplibregl.Map | null>(null)
  const ready = useRef(false)
  const latest = useRef(props)
  const sent = useRef(new Map<string, unknown[]>())
  const [hint, setHint] = useState(false)
  const tipRef = useRef<maplibregl.Popup | null>(null)
  // The zoom hint stays until the reader closes it; once closed it never returns (kept in localStorage).
  const hintDone = useRef({ dismissed: (() => { try { return localStorage.getItem(HINT_KEY) === 'closed' } catch { return false } })() })
  useEffect(() => {
    latest.current = props
  })

  useEffect(() => {
    // One tile worker on a phone (Safari's default is up to three, each holding its own copy of decoded tiles).
    if (latest.current.phone) maplibregl.setWorkerCount(1)
    const map = new maplibregl.Map({
      container: box.current!, style: BASEMAP, bounds: NYC, fitBoundsOptions: { padding: 20 },
      attributionControl: { compact: true }, maxPitch: 0, dragRotate: false,
      // On a desktop plain scrolling reads the story, even over the map, and Ctrl (⌘ on a Mac) + scroll zooms it (the
      // wheel handler below). On a phone the map has its own pane, so it takes ordinary gestures.
      scrollZoom: false,
      // A phone's 3x canvas is a common cause of browser crashes; 2x looks the same on a map. Phones also keep fewer
      // tiles and stop short of street level, since iOS Safari closes a tab that holds too much map in memory.
      // Each whole zoom level is a fresh set of basemap tiles to fetch, decode and label; on a phone the map caches
      // tiles for two levels only and drops street names and shields (see the load handler). It draws at 2x: 1.5x
      // blurred the stations and labels without stopping the crashes.
      pixelRatio: Math.min(window.devicePixelRatio || 1, 2),
      maxTileCacheSize: latest.current.phone ? 24 : 60,
      maxTileCacheZoomLevels: latest.current.phone ? 2 : 5,
      // MapLibre would otherwise resize its canvas on every change to its pane (each frame of a drag of the pane's
      // edge); the debounced observer below resizes it once the pane settles.
      trackResize: false,
      maxZoom: latest.current.phone ? 16 : 18,
      fadeDuration: latest.current.phone ? 0 : 300,
    })
    map.touchZoomRotate.disableRotation()
    // Ctrl or ⌘ + wheel (and a trackpad pinch, which arrives as one) zooms about the pointer; a plain wheel scrolls the
    // page and shows a hint on how to zoom.
    const wheel = (e: WheelEvent) => {
      if (latest.current.phone) return
      if (e.ctrlKey || e.metaKey) {
        e.preventDefault()
        const r = map.getCanvasContainer().getBoundingClientRect()
        const dz = Math.max(-1, Math.min(1, -e.deltaY / (e.deltaMode === 1 ? 6 : 120)))
        map.easeTo({ zoom: map.getZoom() + dz, around: map.unproject([e.clientX - r.left, e.clientY - r.top]), duration: 0 })
        return
      }
      if (!hintDone.current.dismissed) setHint(true)
    }
    map.getCanvasContainer().addEventListener('wheel', wheel, { passive: false })
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right')
    mapRef.current = map
    map.on('error', (e) => console.error('map:', e.error?.message ?? e))
    map.on('load', () => {
      // A phone's pane is small: the route, walk zones and stations are drawn finer there.
      const ph = latest.current.phone
      for (const layer of map.getStyle().layers ?? []) {
        if (layer.type === 'background') map.setPaintProperty(layer.id, 'background-color', SHEET)
        else if (layer.type === 'fill' && /water/.test(layer.id)) map.setPaintProperty(layer.id, 'fill-color', WATER)
        else if (layer.type === 'fill' && /landuse|park|landcover/.test(layer.id)) map.setPaintProperty(layer.id, 'fill-opacity', 0.3)
        else if (layer.type === 'symbol' && /poi|housenumber/.test(layer.id)) map.setLayoutProperty(layer.id, 'visibility', 'none')
        // A phone keeps place and water names but not street names, shields or buildings: the labels cost glyph fetches
        // and placement at every zoom level, the buildings the most geometry.
        if (ph && (/^highway-name|shield|waterway_line_label|water_name_line_label/.test(layer.id) || layer.id === 'building')) map.setLayoutProperty(layer.id, 'visibility', 'none')
      }
      // The points and districts are cut into tiles up to zoom 12 and 13 and enlarged beyond (a metre or two at most),
      // so zooming in does not re-cut thousands of points at every level.
      map.addSource('districts', { type: 'geojson', data: EMPTY, maxzoom: 13 })
      map.addLayer({ id: 'district-fill', type: 'fill', source: 'districts', paint: { 'fill-color': ['coalesce', ['get', 'fill'], 'rgba(0,0,0,0)'],
        // Lighter as the reader nears a named project, so its streets show through rather than a block of colour.
        'fill-opacity': ['interpolate', ['linear'], ['zoom'], 10.5, 0.86, 12.5, 0.45, 14.5, 0.18] } })
      map.addLayer({ id: 'district-edge', type: 'line', source: 'districts', paint: { 'line-color': 'rgba(29, 34, 48, 0.5)', 'line-width': 0.7 } })
      map.addLayer({ id: 'district-hot', type: 'line', source: 'districts', filter: ['==', ['get', 'district'], -1], paint: { 'line-color': INK, 'line-width': 3 } })
      map.addSource('pts', { type: 'geojson', data: EMPTY, maxzoom: 12 })
      map.addLayer({ id: 'pts', type: 'circle', source: 'pts',
        layout: { 'circle-sort-key': ['-', 0, ['get', 'm']] },
        paint: { 'circle-color': ['get', 'tint'], 'circle-radius': size('m'), 'circle-stroke-color': '#ffffff', 'circle-stroke-width': 0.8, 'circle-opacity': 0.9 } })
      // A hovered builder's money at each point, in its tint, over the faded whole.
      map.addLayer({ id: 'pts-hl', type: 'circle', source: 'pts', layout: { visibility: 'none' },
        paint: { 'circle-radius': size('m'), 'circle-stroke-color': '#ffffff', 'circle-stroke-width': 0.8, 'circle-opacity': 0.95 } })
      map.addSource('zones', { type: 'geojson', data: EMPTY })
      map.addLayer({ id: 'zones-fill', type: 'fill', source: 'zones', paint: { 'fill-color': ['step', ['get', 'residents'], ...PEOPLE.flatMap(([v, c], i) => (i === 0 ? [c] : [v, c]))] as never, 'fill-opacity': 0.55 } })
      map.addLayer({ id: 'zones-edge', type: 'line', source: 'zones', paint: { 'line-color': INK, 'line-width': ph ? 0.8 : 1.2 } })
      map.addSource('rail', { type: 'geojson', data: EMPTY })
      map.addLayer({ id: 'rail-other', type: 'line', source: 'rail', filter: ['!=', ['get', 'line'], 'Penn Station Access'], layout: { 'line-cap': 'round', 'line-join': 'round' },
        paint: { 'line-color': ['match', ['get', 'line'], ...Object.entries(LINE_TINT).flat(), INK] as never, 'line-width': ph ? 2 : 2.5, 'line-opacity': 0.8 } })
      map.addLayer({ id: 'rail-case', type: 'line', source: 'rail', filter: ['==', ['get', 'line'], 'Penn Station Access'], layout: { 'line-cap': 'round', 'line-join': 'round' }, paint: { 'line-color': '#ffffff', 'line-width': ph ? 5 : 7 } })
      map.addLayer({ id: 'rail-psa', type: 'line', source: 'rail', filter: ['==', ['get', 'line'], 'Penn Station Access'], layout: { 'line-cap': 'round', 'line-join': 'round' }, paint: { 'line-color': LINE_TINT['Penn Station Access'], 'line-width': ph ? 3 : 4 } })
      // The Manhattan terminals: Grand Central, where New Haven Line trains end today, and Penn Station, where the
      // project takes them (rail_terminals).
      const terminal = ['==', ['get', 'line'], 'terminal'] as never
      map.addLayer({ id: 'terminals', type: 'circle', source: 'rail', filter: terminal,
        paint: { 'circle-radius': ph ? 4 : 5.5, 'circle-color': INK, 'circle-stroke-color': '#ffffff', 'circle-stroke-width': 2 } })
      map.addLayer({ id: 'terminal-labels', type: 'symbol', source: 'rail', filter: terminal,
        layout: { 'text-field': ['format', ['upcase', ['get', 'name']], { 'font-scale': 1 }, '\n', {}, ['get', 'role'], { 'font-scale': 0.85, 'text-font': ['literal', ['Noto Sans Regular']] }] as never,
          'text-font': ['Noto Sans Bold'], 'text-size': ph ? 10 : 12, 'text-max-width': 14,
          // Penn Station's name to the west of its point and Grand Central's to the east, always shown: the two are
          // close enough at plate zoom for their labels to collide and drop out.
          'text-anchor': ['match', ['get', 'code'], 'NYK', 'right', 'left'] as never, 'text-justify': ['match', ['get', 'code'], 'NYK', 'right', 'left'] as never,
          'text-offset': ['match', ['get', 'code'], 'NYK', ['literal', [-0.9, 0]], ['literal', [0.9, 0]]] as never, 'text-allow-overlap': true, 'text-ignore-placement': true },
        paint: { 'text-color': INK, 'text-halo-color': '#ffffff', 'text-halo-width': 2 } })
      map.addSource('stations', { type: 'geojson', data: EMPTY })
      map.addLayer({ id: 'stations', type: 'circle', source: 'stations',
        paint: { 'circle-radius': ['interpolate', ['linear'], ['sqrt', ['coalesce', ['get', 'residents'], 0]], 0, ph ? 4 : 8, 100, ph ? 4 : 8, 230, ph ? 6 : 13] as never, 'circle-color': '#ffffff', 'circle-stroke-color': INK, 'circle-stroke-width': ph ? 2 : 3 } })
      map.addLayer({ id: 'station-labels', type: 'symbol', source: 'stations',
        layout: { 'text-field': ['get', 'label'], 'text-font': ['Noto Sans Bold'], 'text-size': ph ? 10 : 12, 'text-offset': [0, ph ? 0.9 : 1.5], 'text-anchor': 'top', 'text-transform': 'uppercase', 'text-letter-spacing': ph ? 0.04 : 0.08 },
        paint: { 'text-color': INK, 'text-halo-color': '#ffffff', 'text-halo-width': ph ? 1.5 : 2 } })
      // A station's name and residents within 800 m (an estimate), on hover, or on tap where nothing hovers.
      const tip = new maplibregl.Popup({ closeButton: false, closeOnClick: false, offset: 12, className: 'station-tip' })
      tipRef.current = tip
      const showTip = (e: maplibregl.MapLayerMouseEvent) => {
        const f = e.features?.[0]
        if (!f || f.geometry.type !== 'Point') return
        const n = f.properties?.residents
        tip.setLngLat(f.geometry.coordinates as [number, number])
          .setHTML(`<b>${f.properties?.label ?? ''}</b><br>${n ? `${Number(n).toLocaleString()} residents within 800 m <i class="est" title="Estimate"></i>` : ''}`)
          .addTo(map)
      }
      map.on('mousemove', 'stations', (e) => { map.getCanvas().style.cursor = 'pointer'; showTip(e) })
      map.on('mouseleave', 'stations', () => { map.getCanvas().style.cursor = ''; tip.remove() })
      map.on('click', 'stations', showTip)
      map.on('click', (e) => { if (!map.queryRenderedFeatures(e.point, { layers: ['stations'] }).length) tip.remove() })
      ready.current = true
      sendData(map, latest.current, sent.current)
      moveCamera(map, latest.current, false)
      emphasise(map, latest.current)
    })
    // Resized once the pane stops changing: dragging the pane's edge would otherwise rebuild the canvas every frame.
    let wait = 0
    const resize = new ResizeObserver(() => { clearTimeout(wait); wait = window.setTimeout(() => map.resize(), 120) })
    resize.observe(box.current!)
    return () => { clearTimeout(wait); resize.disconnect(); map.remove() }
  }, [])

  // Data goes to the map only when a source's inputs change; the camera moves only when cameraKey does, so a hover,
  // a toggle or the reader's own zoom never snaps it back.
  useEffect(() => {
    if (mapRef.current && ready.current) sendData(mapRef.current, latest.current, sent.current)
    if (view.kind !== 'stations') tipRef.current?.remove()
  }, [view, groups, rail, districts, spots])

  useEffect(() => {
    if (mapRef.current && ready.current) moveCamera(mapRef.current, latest.current, true)
  }, [cameraKey])

  useEffect(() => {
    if (mapRef.current && ready.current) emphasise(mapRef.current, latest.current)
  }, [highlight])

  useEffect(() => {
    if (mapRef.current && ready.current) mapRef.current.setFilter('district-hot', ['==', ['get', 'district'], props.hotArea ? Number(props.hotArea) : -1])
  }, [props.hotArea])

  // Numbered markers for the projects a plate names, drawn as page elements so they stay sharp at any canvas scale and
  // take a tap or click like the list: choosing one goes to it, choosing it again lets go.
  const markers = useRef<{ id: string; el: HTMLButtonElement; m: maplibregl.Marker }[]>([])
  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    markers.current.forEach((x) => x.m.remove())
    markers.current = spots.map((s, i) => {
      // MapLibre positions the wrapper with a transform, so the button inside carries the hover scale.
      const wrap = document.createElement('div')
      const el = document.createElement('button')
      el.type = 'button'
      el.className = 'spot-marker'
      el.textContent = String(i + 1)
      el.setAttribute('aria-label', `${i + 1}: ${s.title}`)
      el.addEventListener('click', (e) => { e.stopPropagation(); latest.current.onPick(s) })
      el.addEventListener('mouseenter', () => latest.current.onHot(s.id))
      el.addEventListener('mouseleave', () => latest.current.onHot(null))
      wrap.append(el)
      return { id: s.id, el, m: new maplibregl.Marker({ element: wrap }).setLngLat([s.lon, s.lat]).addTo(map) }
    })
  }, [spots])
  useEffect(() => {
    for (const x of markers.current) {
      x.el.classList.toggle('on', view.focus?.id === x.id)
      x.el.classList.toggle('hot', hot === x.id)
      x.m.getElement().style.zIndex = hot === x.id ? '3' : view.focus?.id === x.id ? '2' : '1'
      x.el.setAttribute('aria-pressed', String(view.focus?.id === x.id))
    }
  }, [spots, view.focus, hot])

  return (
    <div className="story-map" aria-label="Map of the plate's subject" role="region">
      <div ref={box} className="story-map-canvas" />
      {hint && (
        <div className="map-hint" role="status">
          Hold {/Mac|iPhone|iPad/.test(navigator.platform) ? '⌘' : 'Ctrl'} and scroll to zoom the map
          <button type="button" aria-label="Close the hint" onClick={() => { hintDone.current.dismissed = true; setHint(false); try { localStorage.setItem(HINT_KEY, 'closed') } catch { /* storage blocked: closed for this visit */ } }}>×</button>
        </div>
      )}
    </div>
  )
}

/** A hovered builder's dots over the rest, set as paint without moving the camera. */
function emphasise(map: maplibregl.Map, { highlight }: Props) {
  map.setPaintProperty('pts', 'circle-opacity', highlight ? 0.1 : 0.9)
  map.setPaintProperty('pts', 'circle-stroke-opacity', highlight ? 0.1 : 1)
  map.setLayoutProperty('pts-hl', 'visibility', highlight ? 'visible' : 'none')
  if (highlight) {
    map.setFilter('pts-hl', ['>', ['get', `m_${highlight}`], 0])
    map.setPaintProperty('pts-hl', 'circle-radius', size(`m_${highlight}`))
    map.setPaintProperty('pts-hl', 'circle-color', tintOf(highlight))
  }
}

function moveCamera(map: maplibregl.Map, { view, spots, padding, phone }: Props, animate: boolean) {
  // Eased in a straight line, never flown: a flight zooms out mid-way and loads tiles for a wide area at every zoom,
  // which on a phone is enough to crash the tab.
  const duration = animate && !reduced() ? (phone ? 700 : 1400) : 0
  const pad = (extra: number) => ({ top: padding.top + extra, bottom: padding.bottom + extra, left: padding.left + extra, right: padding.right + extra })
  const frame = (pts: { lon: number; lat: number }[], extra: number, maxZoom: number) => {
    const xs = pts.map((s) => s.lon), ys = pts.map((s) => s.lat)
    map.fitBounds([[Math.min(...xs), Math.min(...ys)], [Math.max(...xs), Math.max(...ys)]], { padding: pad(extra), maxZoom, duration, linear: true })
  }
  if (view.focus) map.easeTo({ center: [view.focus.lon, view.focus.lat], zoom: phone ? 14 : 14.5, padding, duration, essential: false })
  else if (view.kind === 'spots' && spots.length) frame(spots, 50, 13)
  else if (view.kind === 'stations' && view.stations.length) frame([...view.stations, ...(view.extent ?? [])], 60, 13.5)
  else map.fitBounds(NYC, { padding: pad(10), duration, linear: true })
}

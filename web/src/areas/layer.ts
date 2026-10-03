import type { Feature, FeatureCollection, Geometry } from 'geojson'
import type { Areas } from '../data/load'
import { districtName } from '../ui/format'
import type { AreaMeasure, AreaStat, Level } from './aggregate'
import { colorFor } from './measures'

const KEY: Record<Level, string> = { neighborhoods: 'name', districts: 'district', boroughs: 'borough' }
const EDGE: Record<Level, number> = { neighborhoods: 0.5, districts: 0.8, boroughs: 1.6 }

export function areaName(level: Level, key: string): string {
  return level === 'districts' ? `Community district ${districtName(key)}` : key
}

/** Polygons coloured by the measure, plus one label point per area. Areas with no projects stay blank. */
export function buildAreaLayer(level: Level, areas: Areas, stats: Map<string, AreaStat>, m: AreaMeasure) {
  const vals = [...stats.values()].map((a) => m.value(a)).filter((v): v is number => v !== null)
  const max = Math.max(0, ...vals)
  const min = Math.min(0, ...vals)
  const features: Feature[] = []
  const labels: Feature[] = []
  for (const f of areas[level].features) {
    const key = String(f.properties?.[KEY[level]])
    const a = stats.get(key)
    const v = a ? m.value(a) : null
    if (!a || v === null) continue
    const name = areaName(level, key)
    features.push({ ...f, properties: { key, name, edge: EDGE[level], color: colorFor(m.kind, v, max, min), value: `${m.label}: ${m.format(v)} · ${a.n} projects` } })
    labels.push({ type: 'Feature', properties: { label: m.format(v) }, geometry: { type: 'Point', coordinates: labelPoint(f.geometry) } })
  }
  return { fc: { type: 'FeatureCollection', features } as FeatureCollection, labels: { type: 'FeatureCollection', features: labels } as FeatureCollection, max, min }
}

/** Centre of the largest ring's bounding box: cheap and good enough for a label. */
function labelPoint(g: Geometry): [number, number] {
  const polys = g.type === 'MultiPolygon' ? g.coordinates : g.type === 'Polygon' ? [g.coordinates] : []
  let best: number[][] = []
  let bestArea = -1
  for (const poly of polys) {
    const ring = poly[0] as number[][]
    const xs = ring.map((c) => c[0])
    const ys = ring.map((c) => c[1])
    const area = (Math.max(...xs) - Math.min(...xs)) * (Math.max(...ys) - Math.min(...ys))
    if (area > bestArea) [best, bestArea] = [ring, area]
  }
  const xs = best.map((c) => c[0])
  const ys = best.map((c) => c[1])
  return [(Math.min(...xs) + Math.max(...xs)) / 2, (Math.min(...ys) + Math.max(...ys)) / 2]
}

import type { FeatureCollection, Point } from 'geojson'
import MiniSearch from 'minisearch'
import type { Project } from '../data/types'
import { districtName } from '../ui/format'

export interface Place {
  kind: 'neighborhood' | 'address'
  label: string
  detail: string
  lon: number
  lat: number
  zoom: number
}

interface Doc {
  id: string
  title: string
  ids: string
  where: string
  who: string
}

/** Search text for a project: title, IDs, agencies, matched facility, neighborhood, district, borough. */
export function toDoc(p: Project): Doc {
  const x = p.extra as { fmsTitle?: string; pids?: number[] }
  return {
    id: p.id,
    title: [p.title, x.fmsTitle].filter(Boolean).join(' '),
    ids: [p.id, ...(x.pids ?? []).map(String)].join(' '),
    where: [p.matchedTo, p.neighborhood, p.borough, ...p.districts.map((d) => districtName(String(d)))].filter(Boolean).join(' '),
    who: [...p.agencies, p.sponsor, p.theme, p.subtheme].filter(Boolean).join(' '),
  }
}

export function buildIndex(projects: Project[]) {
  const ms = new MiniSearch<Doc>({
    fields: ['title', 'ids', 'where', 'who'],
    searchOptions: { boost: { ids: 4, title: 2 }, prefix: true, fuzzy: 0.15, combineWith: 'AND' },
  })
  ms.addAll(projects.map(toDoc))
  return ms
}

/** Neighborhood and park places from the DCP NTA boundaries (centroid of the outer ring's bounding box). */
export function neighborhoodPlaces(fc: FeatureCollection): Place[] {
  return fc.features.flatMap((f) => {
    const name = f.properties?.name as string | undefined
    if (!name) return []
    const coords = (f.geometry.type === 'MultiPolygon' ? f.geometry.coordinates.flat(2) : f.geometry.type === 'Polygon' ? f.geometry.coordinates.flat() : []) as number[][]
    if (!coords.length) return []
    const xs = coords.map((c) => c[0])
    const ys = coords.map((c) => c[1])
    return [{
      kind: 'neighborhood' as const, label: name, detail: String(f.properties?.borough ?? ''),
      lon: (Math.min(...xs) + Math.max(...xs)) / 2, lat: (Math.min(...ys) + Math.max(...ys)) / 2, zoom: 14,
    }]
  })
}

export function matchPlaces(places: Place[], q: string, limit = 3): Place[] {
  const t = q.trim().toLowerCase()
  if (t.length < 2) return []
  return places.filter((p) => p.label.toLowerCase().split(/[\s-]+/).some((w) => w.startsWith(t)) || p.label.toLowerCase().startsWith(t)).slice(0, limit)
}

const GEOSEARCH = 'https://geosearch.planninglabs.nyc/v2/autocomplete'

/** Addresses through NYC Planning's GeoSearch (official, keyless). Only queried when the text has a house number. */
export async function searchAddresses(q: string, signal: AbortSignal): Promise<Place[]> {
  if (!/\d/.test(q) || q.trim().length < 4) return []
  const res = await fetch(`${GEOSEARCH}?text=${encodeURIComponent(q)}`, { signal })
  if (!res.ok) return []
  const data = (await res.json()) as FeatureCollection
  const seen = new Set<string>()
  return data.features.flatMap((f) => {
    const label = String(f.properties?.label ?? '').replace(/, USA$/, '')
    const [lon, lat] = (f.geometry as Point).coordinates
    const key = `${lon},${lat}`
    if (seen.has(key)) return []
    seen.add(key)
    return [{ kind: 'address' as const, label: label.split(',')[0], detail: label.split(',').slice(1).join(',').trim(), lon, lat, zoom: 16 }]
  }).slice(0, 3)
}

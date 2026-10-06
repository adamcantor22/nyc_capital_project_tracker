import { adapters } from './programs'
import type { Site } from '../areas/aggregate'
import type { Manifest, Project } from './types'

/** Schema versions this site can read (v3 adds the non-city split, start dates and site areas). */
export const SUPPORTED_SCHEMAS = [2, 3, 4, 5, 6, 7]
const DATA = `${import.meta.env.BASE_URL}data/`

export async function fetchJson<T>(file: string): Promise<T> {
  const res = await fetch(DATA + file)
  if (!res.ok) throw new Error(`Could not load ${file} (${res.status})`)
  return res.json() as Promise<T>
}

export async function loadAll(): Promise<{ manifest: Manifest; projects: Project[] }> {
  const manifest = await fetchJson<Manifest>('manifest.json')
  if (!SUPPORTED_SCHEMAS.includes(manifest.schema_version)) {
    throw new Error(`Data schema ${manifest.schema_version}; this site reads schemas ${SUPPORTED_SCHEMAS.join(', ')}`)
  }
  const known = manifest.programs.filter((p) => adapters[p.id])
  const lists = await Promise.all(known.map((p) => adapters[p.id].load(p, fetchJson)))
  return { manifest, projects: lists.flat() }
}

export type Areas = Record<'neighborhoods' | 'districts' | 'boroughs', import('geojson').FeatureCollection>

export async function loadAreas(): Promise<Areas> {
  const [neighborhoods, districts, boroughs] = await Promise.all(
    ['neighborhoods', 'districts', 'boroughs'].map((n) => fetchJson<import('geojson').FeatureCollection>(`areas/${n}.geojson`)),
  )
  return { neighborhoods, districts, boroughs }
}

/** Every program's sites, by project id (each program's rows name the project by its manifest `key`). */
export async function loadSites(manifest: Manifest): Promise<Map<string, Site[]>> {
  const progs = manifest.programs.filter((p) => adapters[p.id] && p.files.sites)
  const lists = await Promise.all(progs.map((p) => fetchJson<Record<string, unknown>[]>(p.files.sites)))
  const m = new Map<string, Site[]>()
  lists.forEach((rows, i) => {
    for (const r of rows) {
      const id = String(r[progs[i].key])
      const list = m.get(id)
      if (list) list.push(r as unknown as Site)
      else m.set(id, [r as unknown as Site])
    }
  })
  return m
}

import { adapters } from './programs'
import type { Manifest, Project } from './types'

export const SUPPORTED_SCHEMA = 2
const DATA = `${import.meta.env.BASE_URL}data/`

export async function fetchJson<T>(file: string): Promise<T> {
  const res = await fetch(DATA + file)
  if (!res.ok) throw new Error(`Could not load ${file} (${res.status})`)
  return res.json() as Promise<T>
}

export async function loadAll(): Promise<{ manifest: Manifest; projects: Project[] }> {
  const manifest = await fetchJson<Manifest>('manifest.json')
  if (manifest.schema_version !== SUPPORTED_SCHEMA) {
    throw new Error(`Data schema ${manifest.schema_version}; this site reads schema ${SUPPORTED_SCHEMA}`)
  }
  const known = manifest.programs.filter((p) => adapters[p.id])
  const lists = await Promise.all(known.map((p) => adapters[p.id].load(p, fetchJson)))
  return { manifest, projects: lists.flat() }
}

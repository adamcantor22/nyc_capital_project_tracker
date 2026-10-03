import { useEffect, useState } from 'react'
import { loadAll } from './data/load'
import type { Manifest, Project } from './data/types'

export default function App() {
  const [data, setData] = useState<{ manifest: Manifest; projects: Project[] } | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    loadAll().then(setData, (e: Error) => setError(e.message))
  }, [])

  if (error) return <p role="alert">{error}</p>
  if (!data) return <p>Loading projects…</p>
  const current = data.projects.filter((p) => p.status === 'current')
  return (
    <main>
      <h1>NYC capital projects</h1>
      <p>
        {current.length.toLocaleString()} current projects, snapshot {data.manifest.latest_snapshot}
      </p>
    </main>
  )
}

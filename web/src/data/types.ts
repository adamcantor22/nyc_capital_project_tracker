export type Tier = 'A' | 'B' | 'C' | 'D' | 'E' | 'Unplaced'

export interface ProgramEntry {
  id: string
  label: string
  publisher: string
  datasets: string[]
  key: string
  currency: string
  files: Record<string, string>
}

export interface Manifest {
  schema_version: number
  generated_at: string
  latest_snapshot: number
  snapshots: number[]
  programs: ProgramEntry[]
  sources: { dataset_id: string; name: string; source_updated: string }[]
  files: Record<string, { rows: number; bytes: number; fields: string[] }>
}

/** The fields every view reads. Each program's adapter maps its own rows onto this. */
export interface Project {
  id: string
  program: string
  title: string
  agencies: string[]
  sponsor: string | null
  borough: string | null
  district: number | null
  districts: number[]
  neighborhood: string | null
  theme: string
  subtheme: string | null
  phase: string | null
  phaseGroup: string
  status: 'current' | 'dropped'
  budget: number
  spend: number
  spendPct: number | null
  budgetChange: number | null
  budgetCity: number | null
  budgetNonCity: number | null
  forecastCompletion: string | null
  hasSchedule: boolean
  firstReported: number
  lastReported: number
  tier: Tier
  lon: number | null
  lat: number | null
  onMap: boolean
  approximate: boolean
  matchedTo: string | null
  sourceFlag: string | null
  outsideNyc: 'near' | 'far' | null
  /** Program-specific extras (IDs, raw fields) for detail panels. */
  extra: Record<string, unknown>
}

export interface ProgramAdapter {
  id: string
  load(entry: ProgramEntry, fetchJson: <T>(file: string) => Promise<T>): Promise<Project[]>
}

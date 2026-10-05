export type Tier = 'A' | 'B' | 'C' | 'D' | 'E' | 'Unplaced'

export interface ProgramEntry {
  id: string
  label: string
  publisher: string
  datasets: string[]
  key: string
  currency: string
  files: Record<string, string>
  /** When the program's source was last updated (YYYY-MM-DD), for programs without report periods. */
  updated?: string
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
  /** Estimated from CPDB shares; null where unknown (and in schema 2 data). */
  budgetFederal: number | null
  budgetState: number | null
  budgetOther: number | null
  /** Earliest actual phase start (YYYY-MM-DD), when reported. */
  startDate: string | null
  forecastCompletion: string | null
  /** Actual milestone dates and the current phase's start (schema 4; null before). */
  milestones: { designStart: string | null; designEnd: string | null; constructionStart: string | null; constructionEnd: string | null; phaseStart: string | null }
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
  /** Another project's id whose amount already counts this work (an SCA project funded through a city FMS ID):
   * totals leave this one out whenever that project is in the same set (see countable()). */
  countedIn: string | null
  /** Program-specific extras (IDs, raw fields) for detail panels. */
  extra: Record<string, unknown>
}

export interface ProgramAdapter {
  id: string
  load(entry: ProgramEntry, fetchJson: <T>(file: string) => Promise<T>): Promise<Project[]>
}

import { fetchJson } from '../data/load'
import type { Manifest } from '../data/types'

export interface HistoryRow { period: number; budget: number; spend: number | null; phase: string | null; forecast_completion: string | null }
export interface ScheduleSnap {
  period: number
  phase: string | null
  completion_date: string | null
  completion_type: string | null
  variance_days: number | null
  variance_implausible: boolean
  reason: string | null
}
export interface Schedule { pid: number; fms_ids: string[]; managing_agency: string | null; name: string | null; snapshots: ScheduleSnap[] }
export interface FundingRow { fy: number; city: number; non_city: number; spend: number | null }

export interface Details {
  history: Record<string, HistoryRow[]>
  schedulesByPid: Map<number, Schedule>
  funding: Record<string, FundingRow[]>
}

let pending: Promise<Details> | null = null

/** History, schedules and funding load on the first opened project, then stay cached. */
export function loadDetails(manifest: Manifest): Promise<Details> {
  if (pending) return pending
  const files = manifest.programs.find((p) => p.id === 'nyc_capital')!.files
  pending = Promise.all([
    fetchJson<Record<string, HistoryRow[]>>(files.history),
    fetchJson<Schedule[]>(files.schedules),
    fetchJson<Record<string, FundingRow[]>>(files.funding),
  ]).then(([history, schedules, funding]) => ({
    history,
    schedulesByPid: new Map(schedules.map((s) => [s.pid, s])),
    funding,
  }))
  pending.catch(() => (pending = null))
  return pending
}

export const SOURCE_LABEL: Record<string, string> = {
  parks_tracker: 'NYC Parks capital project tracker',
  cpdb_points: 'DCP Capital Projects Database (point)',
  cpdb_polygons: 'DCP Capital Projects Database (footprint)',
  bridge_bin: 'Bridge number (BIN) in the project text, located with NYC DOT Bridge Ratings',
  dot_intersections: 'DOT/DEP street reconstruction intersections',
  geoclient_address: 'Street address in the project text, located with NYC Geoclient',
  named_feature: 'Named place in the title (gazetteer: Geoclient, tax lot or USGS GNIS)',
  named_feature_linear: 'Linear feature named in the title (aqueduct, tunnel, corridor)',
  street_extent: 'Street stretch between two cross streets, on the DCP street centerline',
  street_street_only: 'Whole street within the district, on the DCP street centerline',
  facility_code: 'Facility code in the project ID, matched to the DCP Facilities Database',
  facdb: 'Facility named in the title, matched to the DCP Facilities Database',
  parks_properties: 'Park named in the title, matched to NYC Parks Properties',
  fdny_unit: 'FDNY unit in the title, matched to the DCP Facilities Database',
  nypd_unit: 'NYPD precinct in the title, matched to the DCP Facilities Database',
  dsny_unit: 'DSNY district garage in the title, matched to the DCP Facilities Database',
  doc_unit: 'DOC jail in the title, matched to the DCP Facilities Database',
  neighborhood: 'Neighborhood named in the title (DCP Neighborhood Tabulation Areas)',
  community_district: 'Community board listed in the project record',
  borough: 'Borough listed in the project record',
  citywide: 'Listed as citywide',
  no_borough: 'No usable borough in the project record',
}

export const FLAG_TEXT: Record<string, string> = {
  point_disputed: 'The official location for this project is disputed; see the source-error list.',
  borough_field_wrong: 'The borough listed in the project record appears to be wrong.',
  official_point_rejected: 'The official point was rejected as an error, so the project is shown at a coarser location.',
}

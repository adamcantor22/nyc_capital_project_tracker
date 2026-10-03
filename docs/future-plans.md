# Roadmap

Planned work, in rough priority order. The current state is described by `README.md` and `docs/profile.md`.

## Sequence
1. **Public repository and CI.** Done 2026-10-02. GitHub Actions runs ruff and the unit tests on every push.
2. **Pipeline improvements.** The location work below and the testing backlog. This is the current phase.
3. **Export (`pipeline/export.py`).** Writes the files the site reads (projects, locations, street lines, snapshots) as Parquet/GeoJSON. It applies:
   - the phase-group and theme roll-ups from `docs/ui-plan.md`
   - clamping of implausible schedule variances
   - deduplication by FMS ID
4. **Frontend scaffold and map.** React + Vite + MapLibre GL, with keyless vector tiles (OpenFreeMap or Protomaps), following the tier display rules in `docs/ui-plan.md`.
5. **Deployment to GitHub Pages.** The site is static, so no server is needed.
6. **Remaining views:** filters, heatmap, leaderboard, spend progress.

Open design choice for step 4: per-view JSON files precomputed by the pipeline, or DuckDB-WASM querying the exported Parquet in the browser. DuckDB-WASM is the heavier dependency, but it lets the filters reuse the pipeline's SQL.

## Location enrichment

### Remaining coarse projects
In the latest snapshot, 2,090 projects ($49.4B) are at district or borough level, or unplaced. By what they are:

| Kind | Projects | Budget | Approach |
|---|---|---|---|
| Programs, lump sums, holding codes, citywide work | 561 | $20.8B | Correctly coarse. Network overlays (below) where data exists. |
| Other named places or unclear | 736 | $13.4B | Gazetteer additions, name-matching fixes |
| Named neighborhood or area ("Laurelton Area", "Glendale") | 387 | $6.2B | Candidate neighborhood tier from DCP Neighborhood Tabulation Areas |
| Street, sewer and corridor work | 228 | $6.3B | Street-line parser improvements |
| Bridges | 54 | $1.9B | Bridge inventory with BINs (state source; to be verified) |
| Numbered units (firehouses, precincts, school buildings) | 124 | $0.8B | Unit parsers, below |

The classification is regex-based, so the counts are approximate.

### Public-facing facilities (next)
Facilities residents know and use are prioritised by public interest, not budget. Share placed at point level (Tier A or B), all projects:

| Group | Projects | At point level |
|---|---|---|
| CUNY | 313 | 86% |
| Hospitals (HHC) | 381 | 82% |
| Libraries | 154 | 81% |
| Parks | 1,656 | 80% |
| Fire (FDNY) | 125 | 77% (was 9%) |
| Homeless services (DHS) | 121 | 64% |
| Police (NYPD) | 122 | 43% |
| Culture (DCLA) | 137 | 41% |
| Jails (DOC) | 39 | 33% |
| Sanitation (DSNY) | 91 | 29% |
| Aging (DFTA) | 11 | 27% |

FacDB holds the facilities for each group. These are the candidate methods; reach counts coarse projects matching the pattern, so it's an upper bound, not a validated number:

| Method | Reach | Budget | Notes |
|---|---|---|---|
| DCLA institution codes (`PV022` = the Met, `PV176` = Bronx Zoo) plus title abbreviations (MMA, WCS, NYBG) → FacDB cultural institutions | 76 | $504M | 51 share a code with a Tier A project, for validation |
| Library matching fixes | ~20 | ~$250M | Break ties by client agency (Fort Washington Library vs Fort Washington Park); keep "East" in "East Flushing"; lead-word rule after "NYPL Carnegie-"; extra words in FacDB names |
| DSNY district garages ("BK 11", "Queens 8/10/12") and marine transfer stations → FacDB DSNY garages | 33 | $803M | Includes the $531M Bronx 9/10/11 garage |
| NYPD precinct numbers ("7 PCT", "49TH PCT") → FacDB police stations | 25 | $103M | |
| DOC Rikers and Hart Island facilities (GRVC, OBCC, RNDC, powerhouse) → FacDB correctional facilities, or the island | 21 | $196M | |
| EDC campuses: FMS ID prefixes `BN` (Brooklyn Navy Yard), `GO` (Governors Island), `BA` (Brooklyn Army Terminal) | ~50 | ~$0.8B | Their Tier A projects cluster tightly |
| DFTA older adult centers | 8 | $36M | Small |

Shelter locations (DHS) stay at whatever precision the agencies publish; some shelters' locations are confidential by design.

### Done
- **FDNY unit numbers** (2026-10-02, `pipeline/units.py`): 88 projects placed, $317M; 89.9% fall in the community district the project lists. Still coarse: Fort Totten and Randall's Island training campuses (about 15 projects; candidates for the gazetteer), the Brooklyn and Bronx/Queens communications offices, and multi-site energy programs.
- **HHC and CUNY facility codes** (2026-10-02, `pipeline/facility_codes.csv`): 440 projects placed, 87.7% within 500 m of Tier A where both exist. What remains:
  - **Network codes** spanning several sites: HHC `12` (Gouverneur, Judson), `22` (Gotham Brooklyn clinics), `27` (Cumberland, Bedford). Title name matching still applies to these.
  - **Sites not in FacDB:** Gotham LeFrak, Far Rockaway, Neponsit; CUNY Macaulay Honors College and the School of Journalism.
  - **Central programs:** CUNY `CA` IDs with no embedded campus, and multi-campus programs (`CW`).
- **Agency-aware name matching** and the **borough-based jails** (2026-10-02).

### Unresolved placements
- **Placeholder community boards:** 24 of 140 DCAS energy projects (`ACE…`, `SOLAR…`) list "Brooklyn 01" whatever the site. Board-based checks and Tier C placements for these programs are unreliable.
- **Engine 326:** FacDB places it in Queens 11, while the project lists Queens 08.
- **Suspect Tier A points (CPDB polygons):** `BY024-012` and `BY025-012` (Haitian Studies Institute, a Brooklyn College institute) sit in lower Manhattan; `CC026-013` (Aaron Davis Hall, on the City College campus) sits near BMCC. Both are 10–12 km from the campus and need checking against another source.
- **`C11421STC`:** a $433M program-management contract for the borough-based jails. It is currently unplaced. One option is to attribute it to the four jail sites.
- **`P-4SUNRSE` ("Sunrise Stables Acquisition"):** this is matched to Sunrise Playground, which may be wrong. It needs verification before it goes into the golden set.

### Network programs
- Programs such as resurfacing, pedestrian ramps and signal work are funded through program-level FMS IDs, but carried out at many sites.
- Operational datasets show where the work happens, such as DOT in-house resurfacing segments (`ffaf-8mrv`, with WKT geometry).
- These link to a program, not to a project, so they belong on the map as program overlays rather than project pins.

### Water supply projects outside NYC
DEP projects at Kensico, Hillview and the Catskill/Delaware systems are already located through USGS GNIS. The map treatment follows `docs/ui-plan.md`:
- Sites within 30 km of the city extend the map extent.
- More distant sites get an edge-of-map marker pointing toward them.

## New data domains

### MTA capital program
- Candidate source: "MTA Capital Dashboard Project Locations" (`wcsa-vkhf` on data.ny.gov), which includes coordinates. Its keys and coverage have not yet been assessed.
- data.ny.gov runs Socrata, so `pipeline/socrata.py` works with a different base URL.
- MTA projects have no FMS ID, so they are a separate layer or view, not merged into city projects.

### State capital investment in the NYC area
- **Goal:** compare city and state capital priorities (where each spends, and on what) in the five boroughs and the surrounding region, across all state agencies.
- **Candidate sources, to be assessed:**
  - the NYS enacted capital plan and capital budget
  - state agency project lists on data.ny.gov (NYSDOT, DASNY, state-funded SUNY/CUNY work, Empire State Development)
  - the State Comptroller's capital spending data
- **Requirements:**
  - **Locations:** state data has no FMS IDs and a different schema, so it needs its own location work (county, municipality or address).
  - **Categories:** a shared category scheme (transport, water, parks, health, education, housing) applied to both city and state projects.
  - **Co-funding:** city-state co-funded projects can appear in both datasets, so double counting must be handled.

### City budget context (to be scoped)
- **Idea:** set capital spending against the city's whole budget, operating as well as capital. For example: what share of capital projects goes to libraries, compared with libraries' share of total city funding?
- **Open questions:** which sources (the Adopted Budget and Financial Plan, the Comptroller's spending data, Checkbook NYC), how agencies and units of appropriation map onto capital agencies, and how to compare money committed over several years with annual operating spending.

### Private development
- **Candidate sources:** DOB job filings and permits (stories, height, status), Certificates of Occupancy, and the DCP Housing Database. All carry BBL or BIN, so they locate precisely.
- **Separate model:** there is no public budget or variance, only milestones (filed, permitted, under construction, completed). This is a separate layer and schema, not an extension of the capital-project tables.

## Testing
In place: unit tests, data checks on the built database, schema-drift checks, ruff, and CI.

Backlog:
- **Golden set:** grow `tests/golden_locations.csv` from 24 rows to about 50, prioritising Tier B placements verified against an independent source.
- **Data checks in CI:** these need the built database, so they run locally. A scheduled job that runs the full pipeline would move them to CI.
- **Frontend tests:** Vitest component tests and a Playwright smoke test of the map, once `web/` exists.
- **End-to-end fixture test:** the full pipeline on a small offline fixture dataset. Low priority, because the data checks cover most of the same risk.

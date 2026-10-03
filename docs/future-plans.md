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

### District- and borough-only projects
In the latest snapshot, 1,891 projects (18.2% of budget) are placed only at district or borough level.

- **HHC and CUNY facility codes** (next). About 530 projects and $3.6B, where the location is encoded only as a facility code:
  - CUNY FMS ID prefixes (`ME`, `YC`, `QB`) identify campuses.
  - HHC title prefixes (`KINGS:`, `NCB`) and numeric FMS ID prefixes identify hospitals; all Bellevue projects start with `11`.
  - Method: learn each code's location from projects that already have Tier A coordinates, accepting a code only where those points cluster tightly. This alone places about 100 projects. A small code table resolved through FacDB, and checked against the learned clusters, should place most of the rest.
- **Cultural institutions referred to by abbreviation** (e.g. "MMA" for the Metropolitan Museum of Art). These need a small DCLA institution gazetteer.
- **Programs** (sidewalk repairs, tree planting by fiscal year, lump sums). About 240 projects, $5.2B. Borough level is the correct precision for these, unless network overlays (below) are added.

### Unresolved placements
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

### Private development
- **Candidate sources:** DOB job filings and permits (stories, height, status), Certificates of Occupancy, and the DCP Housing Database. All carry BBL or BIN, so they locate precisely.
- **Separate model:** there is no public budget or variance, only milestones (filed, permitted, under construction, completed). This is a separate layer and schema, not an extension of the capital-project tables.

## Testing
In place: unit tests, data checks on the built database, schema-drift checks, ruff, and CI.

Backlog:
- **Golden set:** grow `tests/golden_locations.csv` from 18 rows to about 50, prioritising Tier B placements verified against an independent source.
- **Profile:** add 100 m and 250 m columns to the Tier B validation table. Current values: 69.6% within 100 m, 78.9% within 250 m, 85.5% within 500 m; median error 27 m.
- **Data checks in CI:** these need the built database, so they run locally. A scheduled job that runs the full pipeline would move them to CI.
- **Frontend tests:** Vitest component tests and a Playwright smoke test of the map, once `web/` exists.
- **End-to-end fixture test:** the full pipeline on a small offline fixture dataset. Low priority, because the data checks cover most of the same risk.

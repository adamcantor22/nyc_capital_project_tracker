# Future plans

Ideas agreed in principle but not yet scheduled. Current work lives in commits and `docs/profile.md`.

## Sequencing (agreed 2026-10-02)
For now: keep improving the data pipeline, methodically, with no time pressure. The visible work comes after, in this order:
1. **Public repo + CI.** GitHub, plus Actions running ruff and the unit tests. Done first, ahead of the rest.
2. **`pipeline/export.py`:** writes what the site reads (projects, locations, street lines, snapshots) as Parquet/GeoJSON. Decide here:
   - the phase-group and theme roll-ups
   - clamping the bad variance values
   - deduplicating by FMS ID
3. **`web/` scaffold and the map first.** React + Vite + MapLibre GL, with keyless tiles such as OpenFreeMap or Protomaps. Follow the tier display rules in `docs/ui-plan.md`.
4. **Deploy to GitHub Pages.** The site is static, so there's no server.
5. **Remaining views,** one at a time: filters, heatmap, leaderboard, spend progress.

Open choice for step 3: pre-computed JSON per view, or DuckDB-WASM (SQL in the browser over the exported Parquet). DuckDB-WASM is heavier but reuses the pipeline's SQL.
Why the visible work matters: the project is also a portfolio piece. A live map, a public repo and green CI are what a reviewer sees first.

## New data domains

### MTA capital program (state level)
- Candidate source: "MTA Capital Dashboard Project Locations" (`wcsa-vkhf`), which has latitude/longitude. Not yet checked for keys or coverage.
- The state portal (data.ny.gov) uses the same Socrata API, so `pipeline/socrata.py` should work with a different base URL.
- Open question: MTA projects have no FMS ID. Do they appear as a separate layer or a separate view?

### State capital investment in the NYC area (all agencies, not just MTA)
- **Goal:** compare city and state priorities. Where, and on what, does each spend capital money in the five boroughs and nearby?
- **Likely sources, to verify:**
  - NYS capital budget and enacted capital plan data.
  - State agency project lists on data.ny.gov, e.g. NYSDOT, DASNY, SUNY/CUNY state-funded projects, Empire State Development.
  - The Open Budget / Comptroller capital spending files.
- **Hard part:** the state data won't share FMS IDs or the city's schema. It needs its own location work (county, municipality or address) and a common category scheme so the city/state comparison is apples to apples, e.g. mapping both to transport, water, parks, health, education and housing.
- **Watch for double counting:** some projects are city-state co-funded and may appear in both datasets.

### Private development (e.g. supertall progress)
- Candidate sources: DOB job filings and permits (stories, height, status), Certificates of Occupancy, and the DCP Housing Database. All carry BBL/BIN, so they geocode well.
- This is a different model from capital projects: no city budget or variance, only milestones (filed, permitted, under construction, completed). Plan it as its own layer and schema rather than forcing it into capital-project tables.

## Location enrichment beyond the current step
- **Network programs** (resurfacing, pedestrian ramps, signals, real-time signs and similar):
  - Look for operational datasets that show where the work happens, such as DOT in-house resurfacing segments (`ffaf-8mrv`, which has WKT geometry).
  - These link to a program, not to an FMS ID, so show them as program overlays and never as project pins.
- **Out-of-NYC water supply projects** (DEP: Kensico, Hillview, Catskill/Delaware systems). They're located now (USGS GNIS), but the map treatment is still to do:
  - Near facilities such as Hillview and Kensico in Westchester: extend the map extent.
  - Distant facilities such as the Catskill and Delaware reservoirs: show an edge-of-map marker pointing in their direction.
- **Remaining district/borough-only projects.** In the latest snapshot, 1,891 projects, 18.2% of budget:
  - **Next: HHC/CUNY facility codes.** About 530 projects and $3.6B, where the place is only a code.
    - CUNY FMS prefixes like `ME`, `YC` and `QB` mark campuses. HHC title prefixes (`KINGS:`, `NCB`) and numeric FMS prefixes (all Bellevue projects start with `11`) mark facilities.
    - A tested approach: learn each code's location from projects that already have Tier A coordinates and share the code, accepting a code only when those points cluster tightly. That places 101 projects reliably. A small code table resolved through FacDB, checked against the learned clusters, would reach most of the rest.
  - **Done 2026-10-02:** the borough-based jails (official ZAP BBLs) and agency-aware name matching (+109 projects).
  - **Shorthand cultural institutions** ("MMA" for the Metropolitan Museum of Art) are still unmatched. A small DCLA institution gazetteer would cover them.
  - **Programs** (prior-notice sidewalks, tree planting by fiscal year, lump sums): about 240 projects, $5.2B. Borough level is the honest answer for these, or network overlays (above).
- **Open placement questions:**
  - **`C11421STC`:** a $433M program/project management contract for the new jails. It's unplaced; it could instead be shown at the four jail sites.
  - **"Sunrise Stables Acquisition" (`P-4SUNRSE`):** it matches Sunrise Playground, which may be wrong. This is unverified, so it isn't in the golden set yet.

## Testing
Unit tests, data checks on the built DB, schema-drift checks and ruff are in place. Still to do:
- **Golden set:** started in `tests/golden_locations.csv` (18 rows). Grow it to about 50, especially with Tier B placements checked against a source.
- **Profile metric:** add 100 m and 250 m columns to the Tier B validation table. At last check, Tier B was 69.6% within 100 m, 78.9% within 250 m and 85.5% within 500 m, with a 27 m median.
- **CI:** a GitHub Actions run of `ruff` and the unit tests on every push. This is in progress as Sequencing step 1. Data checks need the built DB, so they stay local, or move to a scheduled job that runs the pipeline.
- **Frontend tests:** component tests with Vitest, plus a Playwright smoke test of the map, once `web/` exists.
- **End-to-end fixture test:** run the full pipeline on a tiny fixture dataset offline. Lower priority, because the data checks cover most of the same risk.

# Future plans

Ideas agreed in principle but not yet scheduled. Current work lives in commits and `docs/profile.md`.

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
- **Remaining district/borough-only projects** (about 2,000 in the latest snapshot; profiled 2026-10-02):
  - Borough-based jails: 5 projects, $15.6B, with no address in their text.
  - Shorthand named sites ("MMA", "Schomburg"): could be placed by agency-aware name matching.
  - HHC/CUNY facility codes: could be placed with learned code clusters plus a small code table.

## Testing
Unit tests, data checks on the built DB, schema-drift checks and ruff are in place. Still to do:
- **Golden set:** started in `tests/golden_locations.csv` (18 rows). Grow it to about 50, especially with Tier B placements checked against a source.
- **CI:** a GitHub Actions run of `ruff` and the unit tests on every push, once the repo has a remote. Data checks need the built DB, so they stay local, or move to a scheduled job that runs the pipeline.
- **Frontend tests:** component tests with Vitest, plus a Playwright smoke test of the map, once `web/` exists.
- **End-to-end fixture test:** run the full pipeline on a tiny fixture dataset offline. Lower priority, because the data checks cover most of the same risk.

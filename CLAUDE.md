# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A tracker for NYC capital projects, built on NYC Open Data (Socrata) and refreshed Jan/May/Sep. The stack is decided:
- **Pipeline:** Python + DuckDB, exporting Parquet/JSON.
- **Frontend:** static React (Vite) site with no backend. Planned in `web/`, not built yet.

Planned UI: an agency variance leaderboard, a project detail timeline and a map.

## Working agreements

- Work in small steps and commit after each one.
- Ask before adding any dependency: a Python package, a DuckDB extension (e.g. `spatial`) or a new external data service. Current deps are only `duckdb` and `httpx`.
- Be frugal with APIs. Query the local DuckDB instead of re-hitting Socrata or Geoclient. When a new source looks useful, pull it into `data/raw/` once rather than querying it piecemeal.
- Report variance as signed values.
- Never include approximate locations (Tier B/C/C2) in totals.

## Commands

All scripts run from the repo root with the venv Python. They import their sibling modules, so call them as `pipeline/x.py`. Keys live in `.env` (gitignored): `SOCRATA_APP_TOKEN` and `GEOCLIENT_KEY` (Geoclient v2, api-portal.nyc.gov).

```sh
.venv/bin/python pipeline/fetch.py            # 4 core datasets -> data/raw/*.csv (skips if source unchanged; --force)
.venv/bin/python pipeline/fetch_locations.py  # location sources -> data/raw/*.json (+ --refresh-reference)
.venv/bin/python pipeline/ingest.py           # rebuild DuckDB tables from data/raw
.venv/bin/python pipeline/geocode.py          # addresses in project text via Geoclient
.venv/bin/python pipeline/named_features.py   # gazetteer: bridges, plants, reservoirs
.venv/bin/python pipeline/street_lines.py     # street projects as centerline lines
.venv/bin/python pipeline/locations.py        # project_locations: best location per project, by tier
.venv/bin/python pipeline/profile.py          # regenerate docs/profile.md
```

Order matters: geocode, named_features and street_lines all feed into locations. Each step is idempotent, and any step can be re-run alone once its inputs exist. There are no tests or linter. Verification is `docs/profile.md`, whose sections check counts, joins, validation precision and coverage. Regenerate it after any pipeline change and diff it.

## Architecture

**Data flow:**
1. **`socrata.py`:** handles paging, metadata and the `rowsUpdatedAt` freshness check. A refresh with nothing new costs one metadata call per dataset.
2. **`data/raw/`:** holds the downloads.
3. **`ingest.py`:** rebuilds `data/capital.duckdb`.
4. **Enrichment scripts:** add location tables.
5. **`locations.py`:** writes `project_locations`.
6. **`profile.py`:** writes the report.

Helpers:
- **`db.py`:** paths, plus `replace_table()`, which bulk-loads via NDJSON because DuckDB `executemany` is far too slow.
- **`geo.py`:** dependency-free geometry: area-weighted centroids, point-in-polygon, haversine and the NYC bounds check.

**Core tables:**
- `project_budget_schedule` (fb86-vt7u)
- `budget_spend_by_fy` (gyhf-rsr3)
- `budget_history` (qj5n-h5qp)
- `schedule_history` (95tx-snak)

These are multi-snapshot tables, keyed by `reporting_period` (YYYYMM), except `budget_history`, which is keyed by `year_month_reported`.

**Data pitfalls (verified):**
- **Many-to-many keys:** PIDs and FMS IDs are many-to-many. `project_budget_schedule` repeats an FMS ID once per linked PID, so naive budget sums double-count. Deduplicate by `fms_id` and prefer the FMS-keyed tables for money.
- **Schedule history is PID-keyed:** `schedule_history` is keyed by PID only. `project_budget_schedule` is the only PID↔FMS bridge.
- **Bad forecast dates:** a few `variance_day` values are about ±365,000, caused by forecast dates like the year 3026. Exclude or clamp them.
- **`community_board` is free text**, in these forms:
  - `Manhattan 01`: a single district.
  - `Queens, Queens 07`: several entries; only `Borough NN` parts name districts.
  - `Queens`: borough only, which is the most common case.
  - `Citywide`.
  - `Brooklyn 99`: a borough-wide placeholder, not a district.

**Location tiers** (`project_locations.tier`). Precedence is in `locations.py`, and the first match wins:

| Tier | Source |
|---|---|
| A | Parks tracker > CPDB points > CPDB polygons > DOT/DEP intersections > Geoclient-geocoded addresses > named point/area features > street extents (stretch between two cross streets) |
| B | Linear named features (aqueducts, tunnels, corridors), whole-street-in-district lines, and title name-matching against FacDB/Parks Properties (`PlaceIndex`; rules in `acceptable()` were tuned against Tier A, so treat its precision as optimistic) |
| C | Community district centroid |
| C2 | Borough centroid |
| none | Citywide, or no usable borough |

Location details:
- **Join keys:**
  - CPDB joins on `projectid`, not `maprojid`, which has an agency prefix.
  - Parks and DOT `fmsid` values carry a `"846 "`-style prefix, which is stripped.
- **`spread_m`:** for street sources this holds the line length; otherwise it is the spread of multi-site points.
- **Outside NYC:** upstate water-supply features are outside the five boroughs. `profile.py` splits them into near (extend the map) and far (edge-of-map marker).

**Enrichment specifics:**
- **`geoclient.py`:** caches every response permanently in `data/raw/geoclient_cache.json`, so re-runs make zero requests.
- **`named_features.csv`:**
  - It is the gazetteer: a regex on the title, plus a lookup that is either a Geoclient string or `gnis:<name>` (the USGS GNIS NY file).
  - Coordinates are never hand-entered.
  - Row order matters, because the first matching pattern wins.
- **`streets.py`:**
  - `normalize()` is applied to both project text and centerline names (`E 72 ST`, `FRANCIS LEWIS BLVD`).
  - Directionals are kept, because `72 ST` and `E 72 ST` are different streets.
- **`street_lines.py`:**
  - Cross streets are found via shared centerline nodes, since segment endpoints are exactly noded.
  - Extents are routed with Dijkstra along the street's own segments.

**DuckDB gotcha:** aliases like `first`, `last`, `rows`, `key`, `matched`, `nulls` and `text` are reserved. Use `as some_name`.

## Docs

- `docs/profile.md`: generated data profile. Don't hand-edit it.
- `docs/future-plans.md`: backlog, covering MTA, state capital investment, private development, network-program overlays and the out-of-NYC map treatment.

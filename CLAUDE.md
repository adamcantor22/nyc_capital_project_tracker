# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A tracker for NYC capital projects, built on NYC Open Data (Socrata) and refreshed Jan/May/Sep. The stack is decided:
- **Pipeline:** Python + DuckDB, exporting Parquet/JSON.
- **Frontend:** static React + TypeScript (Vite) site in `web/` with no backend, deployed to GitHub Pages.

Chosen UI views (detail in `docs/ui-plan.md`): a map with heatmaps, search, an agency variance leaderboard, spend progress, and shared filters. The site reads `data/export/` (see `export.py`).

## Working agreements

- Work in small steps and commit after each one.
- Dependencies: small, well-known libraries and dev tooling can be added without asking. Mention them when you do. Ask first for heavyweight additions or external services that need accounts, keys or payment. Runtime deps live in `requirements.txt`, dev deps (pytest) in `requirements-dev.txt`.
- Be frugal with APIs. Query the local DuckDB instead of re-hitting Socrata or Geoclient. When a new source looks useful, pull it into `data/raw/` once rather than querying it piecemeal.
- Report variance as signed values.
- Location precision and totals:
  - Non-geographic totals (agency, citywide, leaderboard) count every project.
  - Geographic totals count only projects located at least as precisely as the area: borough uses every project with a borough; community district uses Tiers A, B and D (and C where the neighborhood lies in one district); a map viewport, radius or heatmap uses Tier A, plus Tier B labelled approximate. C, D and E points are artificial centroids.
  - Full rules are in `docs/ui-plan.md`.
- Locations come only from official sources: city Open Data, Geoclient, NYS DEC and USGS GNIS. Never scrape and never hand-enter coordinates. Inferred links (which facility a title means) are Tier B and get measured.

## Commands

All scripts run from the repo root with the venv Python. They import their sibling modules, so call them as `pipeline/x.py`. Keys live in `.env` (gitignored): `SOCRATA_APP_TOKEN`, `GEOCLIENT_KEY` (Geoclient v2, api-portal.nyc.gov) and `CENSUS_API_KEY` (free, api.census.gov/data/key_signup.html; used once, the response is cached in `data/raw`).

```sh
.venv/bin/python pipeline/fetch.py            # 4 core datasets -> data/raw/*.csv (skips if source unchanged; --force)
.venv/bin/python pipeline/fetch_locations.py  # location sources -> data/raw/*.json (+ --refresh-reference)
.venv/bin/python pipeline/fetch_sca.py        # SCA school capital, DOE building capacity and school location lists -> data/raw (SCA versions also dated in data/raw/sca)
.venv/bin/python pipeline/ingest.py           # rebuild DuckDB tables from data/raw
.venv/bin/python pipeline/sca.py              # SCA school projects: sca_phases, sca_projects (after fetch_sca)
.venv/bin/python pipeline/census.py           # 2020 population per census tract (CENSUS_API_KEY) -> ref_tract_population
.venv/bin/python pipeline/geocode.py          # addresses in project text via Geoclient
.venv/bin/python pipeline/named_features.py   # gazetteer: bridges, plants, reservoirs
.venv/bin/python pipeline/bridges.py          # BINs in project text -> NYC DOT bridge coordinates
.venv/bin/python pipeline/street_lines.py     # street projects as centerline lines
.venv/bin/python pipeline/locations.py        # project_locations: best location per project, by tier
.venv/bin/python pipeline/sites.py            # project_sites: per-site points and budget shares
.venv/bin/python pipeline/export.py           # JSON/GeoJSON for the site -> data/export/
.venv/bin/python pipeline/profile.py          # regenerate docs/profile.md
```

Order matters: geocode, named_features, bridges and street_lines all feed into locations. Each step is idempotent, and any step can be re-run alone once its inputs exist.

There are two kinds of tests:
- **Unit tests:** offline tests of the parsing, matching, geometry and plumbing logic. They need no network and no `data/`.
- **Data checks** (`tests/test_data.py`, marker `data`): these assert invariants and precision floors on the built `data/capital.duckdb`, and skip when it is absent. Run them after the pipeline. Their thresholds sit a few points below the measured values; if a deliberate change moves a metric, update the threshold and its "when set" comment. `tests/golden_locations.csv` is a growing set of hand-verified placements and known past mistakes, with evidence for each. Add a row whenever a placement is verified or a wrong one is found.

```sh
.venv/bin/python -m pytest                        # everything
.venv/bin/python -m pytest -m "not data"          # unit tests only
.venv/bin/python -m pytest -m data                # data checks only
.venv/bin/python -m pytest -k extract_addresses   # by name
.venv/bin/ruff check pipeline tests               # lint (add --fix for safe fixes)
```

Site (`web/`, Node 24):

```sh
cd web && npm run dev            # dev server; a Vite middleware serves ../data/export at /data/
cd web && npm test               # Vitest unit tests (filters, URL state, search, schedule summary)
cd web && npm run lint && npm run typecheck
scripts/publish_data.sh          # tar data/export -> release data-YYYYMM (gh CLI), then trigger pages.yml
```

- **Deploy:** `.github/workflows/pages.yml` builds `web/` and unpacks the newest `data-*` release into `dist/data/`; it runs on pushes touching `web/` and from `publish_data.sh`. Data never goes into git.
- **Modularity:** `src/data/programs/` holds one adapter per capital program (manifest `programs` entry -> common `Project` fields); `src/filters/registry.ts` and `src/measures/registry.ts` are declarative lists, so a new filter, funding measure or program is one entry. Filters sharing a `group` are ORed: theme and subtheme form one tree (a theme is whole in `theme` or split into subthemes in `subtheme`, kept tidy by `pickTheme`/`pickSub`). Views read only `Project`.
- **Map:** `src/map/` draws Tier A as solid tinted discs, Tier B as hatched discs, C/D/E never as pins: the area view (`src/areas/`) shades neighborhoods, districts or boroughs by a chosen measure, counting projects located at least that precisely (multi-site projects by site share, using each site's `district` and `nta` in `sites.json`). Area measures are a registry (`areas/measures.ts`). Theme tints are the eight validated categorical hues (`themes.ts`); the four smallest themes share slate. MapLibre's worker is emitted beside the bundle by a Vite plugin (`vite.config.ts`).
- **Phone layout** (`usePhone()`, under 760px): the map fills the screen; search and a theme strip float on top; the rail becomes a pull-up sheet (peek, half, full) that slides away under an open project or totals panel.
- **Dates:** parse date strings with `parseDay()` (`src/ui/format.ts`); `new Date('2025-12-01')` is UTC midnight, the previous day in New York.
- **Design:** `PRODUCT.md` (product context) and the direction contract in `.impeccable/surfaces/` (Sanborn Atlas). Use the Impeccable skill for UI work.

`pyproject.toml` holds the pytest and ruff config. It puts `pipeline/` on the test path, so tests import modules by bare name, as the scripts do. `pipeline/validation.py` computes the agreement metrics that both `profile.py` and the data checks use. `docs/profile.md` remains the readable report; regenerate it after any pipeline change and diff it.

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
- **`geo.py`:** dependency-free geometry: area-weighted centroids, `label_point()` (a point inside a shape: the centroid when inside, else a point in the largest part), `central_point()` (the most central of several sites), point-in-polygon, haversine and the NYC bounds check. Polygons are placed by `label_point()` and multi-point projects by `central_point()`, never by a mean: centroids of long, curved or scattered shapes fall offshore or blocks away.
- **`socrata.py`:** requests retry server errors (`RetryTransport`; Open Data returns brief 503s). `check_columns()` raises `SchemaDrift` when an upstream dataset drops or renames a column the pipeline selects. When adding a column to a pipeline step, also add it to the `DATASETS` column lists in `fetch.py` or `fetch_locations.py`; `fetch_locations.py` records the columns it fetched and refetches a dataset once when its list changes.

**Core tables:**
- `project_budget_schedule` (fb86-vt7u)
- `budget_spend_by_fy` (gyhf-rsr3)
- `budget_history` (qj5n-h5qp)
- `schedule_history` (95tx-snak)

These are multi-snapshot tables, keyed by `reporting_period` (YYYYMM), except `budget_history`, which is keyed by `year_month_reported`.

**Data pitfalls (verified):**
- **Many-to-many keys:** PIDs and FMS IDs are many-to-many. `project_budget_schedule` repeats an FMS ID once per linked PID, so naive budget sums double-count. The money record is (`fms_id`, `managing_agency`): 39 FMS IDs in the May 2026 snapshot have two managing agencies with separate budgets (DDC $70.2M and DOT $0.9M on `HWK1669A`). Within one agency the PID rows repeat the same budget. Deduplicate by (`fms_id`, `managing_agency`) and sum across agencies.
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
| A | Parks tracker > bridge numbers (BINs, `bridges.py`) > CPDB points > CPDB polygons > DOT/DEP intersections > Geoclient-geocoded addresses > named point/area features > street extents (stretch between two cross streets) |
| B | Linear named features (aqueducts, tunnels, corridors), whole-street-in-district lines, HHC/CUNY/DCLA facility codes in the FMS ID (`facility_codes.py`), FDNY units, NYPD precincts, DSNY district garages and DOC jails named in the title (`units.py`), then title name-matching against FacDB/Parks Properties (`PlaceIndex`; see below) |
| C | Neighborhood named in the title, as a DCP 2020 NTA centroid (`neighborhoods.py`) |
| D | Community district centroid |
| E | Borough centroid |
| Unplaced | Citywide, or no usable borough. The row has no coordinates; `source` is `citywide` or `no_borough` |

Location details:
- **Join keys:**
  - CPDB joins on `projectid`, not `maprojid`, which has an agency prefix.
  - Parks and DOT `fmsid` values carry a `"846 "`-style prefix, which is stripped.
- **`spread_m`:** for street sources this holds the line length; otherwise it is the distance from the project's point (its most central site) to its farthest site.
- **Name matching (`locations.py`):**
  - A place matches when all of its distinctive (non-`GENERIC`) words appear in the title, in the same borough.
  - Equally good candidates go to one run by a client agency, then to the best full-name fit (`EAST FLUSHING` vs `FLUSHING`). Not for Parks projects, where it chose the centres of large parks. Remaining ties more than 500 m apart are rejected.
  - Titles naming several sites (`MULTI_SITE`: "@ 17 Branch Libraries") are not name-matched.
  - `acceptable()` rejects address-like facility matches. One-word matches need the place to be run or overseen by a client agency of the project: managing, sponsor, or a title prefix like `NYPD - `.
  - FacDB `operator` and `overseer` codes are normalised by `normalize_agency()`: NYCDPR becomes DPR, NYCHHC becomes HHC, DSS becomes DHS, QBPL becomes QPL, and NYCHA stays NYCHA.
  - For facilities, the one word must also lead the title.
  - `location_validation.rule` records which rule admitted each match. Precision is measured in-sample against Tier A, so treat it as optimistic.
  - DOT work, linear work and "Citywide" titles are never name-matched.
- **Outside NYC:** upstate water-supply features are outside the five boroughs. `profile.py` splits them into near (extend the map) and far (edge-of-map marker).

**Enrichment specifics:**
- **`geoclient.py`:** caches every response permanently in `data/raw/geoclient_cache.json`, so re-runs make zero requests. Only the `KEEP` fields are cached. If you add a field, call `forget()` on the affected queries to re-request them.
- **`facility_codes.csv`:** maps the facility code in HHC (`FFYYYYNN`), CUNY (`CCnnn-nnn`, `CA091KG03`) and DCLA (`PVnnn`) FMS IDs to one FacDB row by name and factype. DCLA projects are managed by DCLA, DDC or EDC, so `code_key()` assigns ID prefixes to their owning agency (`PREFIX_OWNERS`). Prefer the row for the venue itself (a PUBLIC MUSEUMS AND SITES, ZOO or STATE HISTORIC PLACE row) over an organisation's row, which may be an office address. Add a code only when titles under it name the facility, or its Tier A projects agree; a data check enforces this. Codes beat title name matching, since in every disagreement the code was right.
- **`units.py`:** parses unit numbers ('EC287', 'Engine Company 65', 'SQ288', 'EMS Station 4'), precincts ('49TH PCT', '26TH, 42ND & 46TH PRECINCTS'), DSNY district garages ('Queens 8/10/12', FacDB 'QE08G GARAGE'; salt sheds excluded, as they often stand apart) DOC jail acronyms ('GRVC', FacDB 'GEORGE R. VIERNO CENTER (GRVC)') and named sites (`SITES`: FDNY's Fort Totten and Randall's Island campuses; Rikers Island for DOC work that names no jail, such as the powerhouse; Hart Island) from titles and FacDB names with the same regexes; a named jail beats the island (`CONTAINERS`); unit numbers are unique citywide, so 'Citywide'-borough projects can be placed. Each unit kind belongs to one agency (`AGENCY`); a FacDB row contributes only its operator's units, and a title's units count only for its client agencies. If any client unit in a title is missing from FacDB the project is not placed, since it may span another building. The source is `<agency>_unit` (`fdny_unit`, `nypd_unit`, `dsny_unit`, `doc_unit`).
- **Validation without Tier A:** `validation.district_agreement()` checks placed points against the one community district a project lists. The board field is noisy (agency-supplied points agree 77–93%; some DCAS energy programs list placeholder boards such as 'Brooklyn 01'), so treat it as a floor and compare sources against each other. It does not suit DSNY garages, which often stand outside the district they serve (the Manhattan 8 garage is in Manhattan 12).
- **`named_features.csv`:**
  - It is the gazetteer: a regex on the title, plus a lookup. The lookup is a Geoclient string, `bbl:<10-digit BBL>` (an official tax lot, e.g. from DCP ZAP, resolved by Geoclient to the lot's label point), or `gnis:<name>` (the USGS GNIS NY file).
  - Cite the source of a BBL in `notes`. The borough-based jails use BBLs from ZAP project 2019Y0061.
  - Coordinates are never hand-entered.
  - Row order matters, because the first matching pattern wins.
- **`streets.py`:**
  - `normalize()` is applied to both project text and centerline names (`E 72 ST`, `FRANCIS LEWIS BLVD`).
  - Directionals are kept, because `72 ST` and `E 72 ST` are different streets.
- **Source errors and the borough check:** `pipeline/source_errors.csv` lists hand-verified errors in the sources (`point_wrong`, `listing_wrong`, `generic_point`, `unclear`), each with evidence. Tier A skips a source marked `point_wrong` or `generic_point` for that project. Any Tier A point more than 2 km outside the listed borough goes to `borough_conflicts`: it is dropped unless the title names the point's borough (`TITLE_BOROUGH`: Parks codes like `Q106`, borough names) or the list says `listing_wrong`. A data check requires every flagged point to be in the list, so add a row with evidence when one appears. `project_locations.source_flag` carries the outcome to each project (`point_disputed`, `borough_field_wrong`, `official_point_rejected`) for the site to show. Only official evidence settles a row; general knowledge leaves it `unclear`. Prefer evidence from official reference data (FacDB, Parks Properties, the centerline).
- **`bridges.py`:** reads BINs from project text ('BIN 2229579', '2-24013-7', '(2232000)', 'BINS: 2241139, 2243410') and locates them with NYC DOT Bridge Ratings (`4yue-vjfc`; its `x_coord_lat` holds latitude). A bare 7-character number counts only when it is a known BIN and the text mentions a bridge. BIN points come ahead of CPDB, which misplaces several bridges by kilometres. The NYS DOT bridge dataset has no coordinates.
- **`sites.py`:** `project_sites` holds one row per known site with a budget share: equal, or `source_proportion` where the Parks tracker gives differing per-entry amounts. Single-site projects get one row (`single`); unplaced projects none. `money.py` computes budgets per (`fms_id`, `managing_agency`); use it for any money total.
- **`sca.py`:** School Construction Authority projects, from SCA's own capital data (`2xh6-psuq`, one row per phase). A project is its DSF number(s) at one building code (`dsf_numbers()` splits fields holding two); rows without a DSF are keyed by type and description. Cost is the 'final estimate of actual costs' (the budget field is 0 on most rows). Rows are additive and never merged on equal amounts (Reso A grants are round sums per school), except reviewed program-level figures copied onto many schools (`sca_repeats.csv`, Project Connect's $445M and $474M): those rows count the school's own spending, and the figure stays in `program_figure`, out of totals. Data checks reconcile counted money with the published estimates and fail on any unreviewed repeated amount of $10M+ on 3+ buildings. The date fields hold placeholders ('PNS', 'FTK', type codes), read as missing.
- **`export.py`:** writes `data/export/` (gitignored): `projects.json` (every FMS ID ever reported, `status` current or dropped), `schedules.json` (per PID), `history.json`, `sites.json`, `funding.json` (city and non-city budget per fiscal year, from `budget_spend_by_fy`), `lines.geojson`, `footprints.geojson`, `areas/*.geojson` (boroughs are DCP's shoreline-clipped outlines, `gthc-hcne`, not a union of districts, which would leave holes at parks and airports) and `manifest.json`. Non-city money is split into `budget_federal`, `budget_state` and `budget_other` by each project's shares in CPDB (`fi59-268w`, planned plus committed; `cpdb_funding` table), an estimate, null where CPDB has no split. `start_date` is the earliest actual phase start; `design_start/end`, `construction_start/end` and `phase_start` are the latest snapshot's actual milestone dates, which the site's one-line "When" reads by phase (`whenLabel()` in `src/ui/format.ts`; the phase wins over a contradicting date). `manifest.json` has a `programs` registry (each capital program, its datasets and files; every project row names its `program`, `nyc_capital` for city projects), so another program is a new entry and files rather than a format change. `tests/test_export.py` pins the project fields; changing them is a format change for the site, so bump `SCHEMA_VERSION`. Districts come from the project's sites (point-in-polygon); `outside_nyc` is `near` within 30 km of the city's edge (Kensico) or `far`.
- **Phase groups and themes:** `phase_groups.csv` maps every raw `current_phase` spelling (compared without case or punctuation) to a group; a data check fails on a new unmapped spelling. `themes.csv` holds three kinds of rule (category, agency, budget-line prefix), each with a theme and optional subtheme; `themes.theme()` applies them in that order.
- **`neighborhoods.py`:** splits NTA names into parts ('Manhattanville-West Harlem') and matches them as whole words in the project's borough. A part followed by a street, water, park or facility word ('Bedford Ave', 'Gravesend Bay') or preceded by 'Grand' doesn't count. It needs a neighborhood in one of the districts the project lists, and several named neighborhoods within 3 km of each other. DOT and DEP are skipped (55–63% precision). `neighborhood_validation` stores the distance from Tier A points to the named neighborhood.
- **`street_lines.py`:**
  - Cross streets are found via shared centerline nodes, since segment endpoints are exactly noded.
  - Extents are routed with Dijkstra along the street's own segments, up to 8 km. When no route is found, the whole street within the project's district is used instead.
  - Range words include `FR`, `BT.` and a dash followed by `A TO B`. A street name may be followed by a few words such as `RECONSTRUCTION` or `PHASE 2` before the range (`TRAILING`).
  - Cross-street pairs share a leading word (`E 80TH & 81ST` means E 81st St; `BAY 20TH & 28TH` means Bay 28th St), and street lists share a suffix (`224 & 223 ST`).

**DuckDB gotcha:** aliases like `first`, `last`, `rows`, `key`, `matched`, `nulls`, `text` and `rule` are reserved. Use `as some_name`.

## Docs

- `docs/profile.md`: generated data profile. Don't hand-edit it.
- `docs/ui-plan.md`: chosen UI views, map and tier display rules, totals rules, phase and theme roll-ups, and open UI questions.
- `docs/future-plans.md`: the roadmap. It covers the build sequence (pipeline work first, then export, map and deploy), remaining location work, new data domains (MTA, state capital, private development) and the testing backlog.
- Repo docs are public. Write them as definitive reference text (what the project does and why), not as a record of discussions or decisions.

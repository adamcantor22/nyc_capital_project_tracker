# NYC Capital Projects Tracker

[![CI](https://github.com/adamcantor22/nyc_capital_project_tracker/actions/workflows/ci.yml/badge.svg)](https://github.com/adamcantor22/nyc_capital_project_tracker/actions/workflows/ci.yml)

A tracker for New York City's capital projects: about 5,600 projects and $160B in budget, across agencies such as DEP, DOT, Parks and DDC. It shows how budgets, spending and schedules change over time, and places each project on a map as precisely as the official data allows.

The source data is published on NYC Open Data and refreshed three times a year (January, May, September). It has no coordinates, so a large part of the pipeline is building project locations from other official sources and measuring how accurate they are.

**Status:** the data pipeline, location enrichment and test suite are working. The web frontend is planned (`docs/ui-plan.md`).

## Data

Core datasets (NYC Open Data / Socrata):

| ID | Contents |
|----|----------|
| [fb86-vt7u](https://data.cityofnewyork.us/d/fb86-vt7u) | Project budget and schedule, keyed by FMS ID |
| [gyhf-rsr3](https://data.cityofnewyork.us/d/gyhf-rsr3) | Budget and spend by fiscal year |
| [qj5n-h5qp](https://data.cityofnewyork.us/d/qj5n-h5qp) | Budget history and variance |
| [95tx-snak](https://data.cityofnewyork.us/d/95tx-snak) | Schedule history and variance |

Three properties of the data shape the design:
- **Two IDs.** Budget data is keyed by FMS ID and schedule data by PID, and the two are many-to-many. Budgets are deduplicated by FMS ID before summing.
- **Signed variance.** Variance is the change since the previous report. A positive budget variance is a budget increase; a positive schedule variance is a later forecast completion.
- **No coordinates.** The project data carries only a borough and a free-text community board.

## Project locations

Each project gets one best location, assigned by tier from official sources only. There is no scraping and no hand-entered coordinates.

| Tier | Method | Sources | Projects | Budget |
|---|---|---|---|---|
| A | Agency geometry joined on FMS ID; street addresses in project text; named facilities (bridges, plants, reservoirs, jail sites); street stretches between two cross streets | DCP Capital Projects Database, Parks capital tracker, DOT/DEP intersections, NYC Geoclient, DCP ZAP tax lots, USGS GNIS, NYS DEC, street centerline | 49.8% | 59.5% |
| B | Hospital, campus and cultural-institution codes in HHC, CUNY and DCLA project IDs; FDNY units, NYPD precincts, DSNY district garages and Rikers jails named in the title ("Engine 287", "49th Pct", "Queens 8/10/12 Garage", "GRVC"); project title matched to a facility or park name in the same borough; whole street within a district; linear features (aqueducts, tunnels) | DCP Facilities Database, Parks Properties, street centerline | 16.9% | 10.7% |
| C | Community district centroid | DCP Community Districts | 7.4% | 6.2% |
| C2 | Borough centroid | DCP Community Districts | 16.5% | 9.7% |
| none | Citywide programs | | 9.3% | 13.9% |

Figures are for the May 2026 snapshot.

Each inferred method is checked against projects whose location is already known:
- **Tier B codes, unit numbers and name matching:** median error 23 m; 71% of placements fall within 100 m and 86% within 500 m.
- **Geocoded addresses:** 95% fall within 500 m of the agency's own coordinates.
- **Named features:** 92% fall within 1 km.
- **Street lines:** 89% fall within 500 m.

Coarse tiers only count toward totals for areas at least as large as their own precision. For example, a borough centroid never feeds a heatmap. `docs/profile.md` has the full coverage and validation report.

## Stack
- **Pipeline:** Python and DuckDB. It fetches from Socrata, the NYC Geoclient API and reference layers, builds and profiles the database, and exports Parquet/JSON for the frontend.
- **Frontend (planned):** a static React (Vite) site with no backend: a map with heatmaps, an agency variance leaderboard, spend progress, and shared filters.

## Layout
- `pipeline/`: fetch, ingest, location enrichment and profiling scripts
- `tests/`: unit tests, data checks on the built database, and `golden_locations.csv`, a set of hand-verified placements
- `docs/profile.md`: the generated data profile and location validation report
- `docs/ui-plan.md`: frontend design and display rules
- `docs/future-plans.md`: the roadmap
- `data/`: raw downloads, the Geoclient cache and `capital.duckdb` (not committed)

## Running the pipeline
1. Install the dependencies:
   ```sh
   python -m venv .venv
   .venv/bin/pip install -r requirements.txt -r requirements-dev.txt
   ```
2. Create a `.env` file with two keys:
   - `SOCRATA_APP_TOKEN`: from NYC Open Data.
   - `GEOCLIENT_KEY`: the "Geoclient v2 User" product at api-portal.nyc.gov.
3. Run the scripts in order:
   ```sh
   .venv/bin/python pipeline/fetch.py            # core datasets; skips sources that haven't changed
   .venv/bin/python pipeline/fetch_locations.py  # location sources; --refresh-reference for slow-changing layers
   .venv/bin/python pipeline/ingest.py           # rebuild DuckDB tables from data/raw
   .venv/bin/python pipeline/geocode.py          # addresses in project text (Geoclient, cached)
   .venv/bin/python pipeline/named_features.py   # gazetteer: bridges, plants, reservoirs, jails
   .venv/bin/python pipeline/street_lines.py     # street stretches on the centerline
   .venv/bin/python pipeline/locations.py        # best location per project, by tier
   .venv/bin/python pipeline/profile.py          # regenerate docs/profile.md
   ```

Every step is idempotent. API responses and downloads are cached, so a re-run against unchanged sources makes almost no network requests.

## Tests
```sh
.venv/bin/python -m pytest -m "not data"   # unit tests (offline; these run in CI)
.venv/bin/python -m pytest -m data         # data checks on the built database
.venv/bin/ruff check pipeline tests
```

The data checks assert invariants, a minimum precision for each location method, and the golden placements. They skip when the database hasn't been built.

# NYC Capital Projects Tracker

[![CI](https://github.com/adamcantor22/nyc_capital_project_tracker/actions/workflows/ci.yml/badge.svg)](https://github.com/adamcantor22/nyc_capital_project_tracker/actions/workflows/ci.yml)

Web-based tracker for NYC capital projects, built on NYC Open Data (Socrata).
Data refreshes Jan/May/Sep.

## Datasets
| ID | Contents |
|----|----------|
| fb86-vt7u | Project budget + schedule (keyed by FMS ID) |
| gyhf-rsr3 | Budget & spend by fiscal year |
| qj5n-h5qp | Budget spend history & variance |
| 95tx-snak | Schedule history & variance |

Rules: PIDs and FMS IDs are many-to-many; variance is reported as signed values.

## Stack (decided)
- Pipeline: Python + DuckDB; fetches from Socrata, profiles, exports Parquet/JSON
- Frontend: React (Vite), static site, no backend
- UI (planned, see `docs/ui-plan.md`): map with heatmaps, agency variance leaderboard, spend progress, shared filters

## Layout
- `pipeline/` fetch, ingest, location enrichment and profiling
- `data/` raw downloads, the Geoclient cache and `capital.duckdb` (gitignored)
- `docs/profile.md` generated data profile; `docs/ui-plan.md` UI decisions; `docs/future-plans.md` backlog
- `tests/` unit tests, data checks on the built DB, and `golden_locations.csv`
- `web/` React app (planned)

## Running the pipeline
Put `SOCRATA_APP_TOKEN` and `GEOCLIENT_KEY` in `.env` (gitignored). Then run in this order:

```sh
.venv/bin/python pipeline/fetch.py            # core datasets; skips unchanged sources
.venv/bin/python pipeline/fetch_locations.py  # location sources; --refresh-reference for slow layers
.venv/bin/python pipeline/ingest.py           # rebuild DuckDB tables from data/raw
.venv/bin/python pipeline/geocode.py          # addresses in project text (Geoclient, cached)
.venv/bin/python pipeline/named_features.py   # gazetteer: bridges, plants, reservoirs
.venv/bin/python pipeline/street_lines.py     # street stretches on the centerline
.venv/bin/python pipeline/locations.py        # best location per project, by tier
.venv/bin/python pipeline/profile.py          # regenerate docs/profile.md
```

## Tests and lint
```sh
.venv/bin/pip install -r requirements.txt -r requirements-dev.txt
.venv/bin/python -m pytest              # unit tests + data checks (data checks skip without the DB)
.venv/bin/ruff check pipeline tests
```

# NYC Capital Projects Tracker

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
- Planned UI: agency variance leaderboard, project detail timeline, map (if locations exist)

## Layout (planned)
- `pipeline/` ingest and profiling
- `data/` raw + DuckDB + exports (gitignored)
- `web/` React app

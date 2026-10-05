# Roadmap

Planned work, in rough priority order. The current state is described by `README.md` and `docs/profile.md`.

## Sequence
1. **Public repository and CI.** Done 2026-10-02. GitHub Actions runs ruff and the unit tests on every push.
2. **Pipeline and location work.** Done for now: location tiers A–E, per-site budget shares, source-error list and the testing backlog below. The remaining location work resumes after step 8.
3. **Export (`pipeline/export.py`).** Done 2026-10-03. Writes JSON and GeoJSON to `data/export/` for every project ever reported (8,171; 5,608 current): projects with money, phase group, theme, location, district and search fields; schedules per PID; budget history per snapshot; per-site budget shares; street lines, CPDB footprints, and district, neighborhood and borough boundaries. About 4 MB compressed. A manifest records the schema version, snapshots and source freshness; data checks pin the project fields. Re-run it after any pipeline change. Not yet exported: `budget_history`'s monthly series back to 2006, which has conflicting duplicate rows within an agency (85 cases) to resolve first.
4. **Product and design context.** Done 2026-10-03: `PRODUCT.md` and a Sanborn Atlas visual direction. `DESIGN.md` is written at the finish review.
5. **Export for modularity.** Done 2026-10-03 (schema v2). A program registry in the manifest, so other capital programs (MTA, SCA, state) can be added as their own layers, and the city / non-city funding split per fiscal year.
6. **Frontend scaffold and map.** Done 2026-10-03, with search, filters, URL state and the project detail panel. React + Vite + MapLibre GL, with keyless vector tiles (OpenFreeMap or Protomaps), following the tier display rules in `docs/ui-plan.md`. Filters, measures, views and program adapters are registries, so a new dimension or program is one entry rather than a rewrite.
7. **Deployment to GitHub Pages.** Done 2026-10-03. The site is static, so no server is needed. The workflow fetches the export from a GitHub Release asset, so data files stay out of the main branch.
8. **Remaining views:** heatmap, leaderboard, spend progress. This is the current phase.
9. **Remaining location work** (below), then new data domains.

The site reads plain JSON and GeoJSON; filters, totals and search run in the browser in JavaScript (5,600 current projects is small). Footprints and history can load on demand.

## Location enrichment

### Remaining coarse projects
In the latest snapshot, 2,090 projects ($49.4B) are at district or borough level, or unplaced. By what they are:

| Kind | Projects | Budget | Approach |
|---|---|---|---|
| Programs, lump sums, holding codes, citywide work | 561 | $20.8B | Correctly coarse. Network overlays (below) where data exists. |
| Other named places or unclear | 736 | $13.4B | Gazetteer additions, name-matching fixes |
| Named neighborhood or area ("Laurelton Area", "Glendale") | ~285 | ~$3.9B | Partly placed as Tier C; the rest name a neighborhood inside a street, water or facility name, or belong to DOT/DEP |
| Street, sewer and corridor work | ~215 | ~$5.8B | Remaining: long corridors known only by borough (Queens Blvd, Rockaway Blvd), streets named without "in/on" ("86th St & Bay Pkwy"), alternate names (Lenox Ave for Malcolm X Blvd), pumping stations named after streets |
| Bridges | 57 | $1.6B | Coarse projects mentioning a bridge, after BIN placement: 11 single "X over Y" bridges ($0.89B; candidate: match X and Y to the carried and crossed features in NYC DOT Bridge Ratings), 16 bridges named without "over" ($0.15B), 30 programs or multi-bridge contracts ($0.62B, mostly not one location) |
| Numbered units (firehouses, precincts, school buildings) | 124 | $0.8B | Unit parsers, below |

The classification is regex-based, so the counts are approximate.

### Public-facing facilities
Facilities residents know and use are prioritised by public interest, not budget. Share placed at point level (Tier A or B), among current projects whose managing or sponsoring agency is the group's; the "was" figures are before the step that targeted the group:

| Group | Projects | At point level |
|---|---|---|
| Culture (DCLA) | 145 | 88% (was 41%) |
| CUNY | 313 | 86% |
| Fire (FDNY) | 125 | 86% (was 9%) |
| Hospitals (HHC) | 384 | 82% |
| Libraries | 172 | 90% (was 81%) |
| Parks | 1,671 | 79% |
| Homeless services (DHS) | 121 | 64% |
| Police (NYPD) | 124 | 56% (was 43%) |
| Jails (DOC) | 39 | 74% (was 33%) |
| Sanitation (DSNY) | 93 | 56% (was 29%) |
| Aging (DFTA) | 12 | 25% |

FacDB holds the facilities for each group. These are the candidate methods; reach counts coarse projects matching the pattern, so it's an upper bound, not a validated number:

| Method | Reach | Budget | Notes |
|---|---|---|---|
| Remaining library names | ~10 | ~$50M | Names made only of generic words ("City Island", "Bronx Library Center", "Court Square"); extra words in FacDB names ("HARRY BELAFONTE 115TH STREET LIBRARY", "BELMONT LIBRARY AND ENRICO FERMI CULTURAL CENTER"); "Pelham Pkwy/Van Nest" caught by the street filter |
| DSNY marine transfer stations and repair shops (Hamilton Ave, North Shore, W 59th St MTS; Cioffe, Queens Central Repair Shop) → FacDB | ~15 | | Named sites, not numbered |
| EDC campuses: FMS ID prefixes `BN` (Brooklyn Navy Yard), `GO` (Governors Island), `BA` (Brooklyn Army Terminal) | ~50 | ~$0.8B | Their Tier A projects cluster tightly |
| DFTA older adult centers | 8 | $36M | Small |

Shelter locations (DHS) stay at whatever precision the agencies publish; some shelters' locations are confidential by design.

### Done
- **FDNY unit numbers and training campuses** (2026-10-02, `pipeline/units.py`): 105 projects placed; 89.9% of unit placements fall in the community district the project lists. Still coarse: the borough communications offices and multi-site energy programs.
- **NYPD precinct numbers** (2026-10-02, `pipeline/units.py`): 38 projects placed at their station house, 20 of them previously at district or borough level; 7 of 8 agree with Tier A within 100 m. Still coarse: named precincts ("Midtown North"), harbor units, Rodman's Neck and other non-precinct sites.
- **DSNY district garages** (2026-10-02, `pipeline/units.py`): 50 projects placed; 14 of 16 agree with Tier A within 500 m (median 23 m). District agreement is low by design: garages often stand outside the district they serve.
- **DOC jails and Rikers Island** (2026-10-02, `pipeline/units.py`): 28 projects placed at a named jail or, for island-wide work (powerhouse, steam tunnels, marina), at Rikers Island. Where CPDB gives a specific jail, placements agree within 2 m.
- **Name-matching tie-breaks** (2026-10-02, `locations.py`): equally good candidates now go to the one run by a client agency, then to the one whose full name best fits the title (Fort Washington Library over Fort Washington Park for an NYPL project; East Flushing over Flushing). Not applied to Parks projects, where it picked the centres of large parks. Titles naming several sites ("@ 17 Branch Libraries") are no longer name-matched. Libraries at point level rose from 81% to 89%; every new validation match is within 40 m.
- **Neighborhood tier (Tier C)** (2026-10-02, `pipeline/neighborhoods.py`): projects naming a DCP 2020 neighborhood are placed at its centroid instead of a district or borough centroid: 102 projects ($2.3B) in the latest snapshot. On projects with known points, 93% fall within 500 m of the named neighborhood. Tiers were renamed to make room: district is now D (was C) and borough E (was C2).
- **Tier A borough check and source-error list** (2026-10-03, `locations.py`, `pipeline/source_errors.csv`): a Tier A point more than 2 km outside the project's listed borough is dropped unless the title names the point's borough; hand-verified errors in `source_errors.csv` are skipped too. 40 projects moved: 20 to a facility, jail, park or neighborhood match, 19 to their district or borough, and 1 to its other Tier A source.
- **Street parser improvements** (2026-10-03, `street_lines.py`): range words `FR`, `BT.` and `– A TO B`, trailing words before a range, shared prefixes in cross-street pairs, shared suffixes in street lists, whole-street fallback when a range can't be routed, and an 8 km cap on ranges. Lines rose from 97 to 108 extents and 219 to 233 whole streets; 11 coarse projects (about $0.5B) placed. 90% of lines fall within 500 m of the project's other official point.
- **Bridges by BIN** (2026-10-03, `pipeline/bridges.py`): BINs in project text located through NYC DOT Bridge Ratings, as a Tier A source ahead of CPDB. 133 projects have a BIN; 14 coarse projects ($0.51B) in the latest snapshot moved to Tier A. 94% agree with the agency's own point within 500 m (median 2 m); the CPDB points that disagree by over 1 km, and four projects whose borough field contradicts their BIN, are in `source_errors.csv`.
- **DCLA institution codes** (2026-10-02, `PVnnn` in `pipeline/facility_codes.csv`): 70 projects placed, $503M; 53 of 57 within 500 m of Tier A (median 30 m). Not yet placed: the Queens Museum and MoMA PS1 (absent from FacDB), the Staten Island Museum (moved to Snug Harbor; FacDB has the old site), the Public Theater (two sites), and smaller organisations whose FacDB row may be an office.
- **HHC and CUNY facility codes** (2026-10-02, `pipeline/facility_codes.csv`): 440 projects placed, 87.7% within 500 m of Tier A where both exist. What remains:
  - **Network codes** spanning several sites: HHC `12` (Gouverneur, Judson), `22` (Gotham Brooklyn clinics), `27` (Cumberland, Bedford). Title name matching still applies to these.
  - **Sites not in FacDB:** Gotham LeFrak, Far Rockaway, Neponsit; CUNY Macaulay Honors College and the School of Journalism.
  - **Central programs:** CUNY `CA` IDs with no embedded campus, and multi-campus programs (`CW`).
- **Agency-aware name matching** and the **borough-based jails** (2026-10-02).

### Unresolved placements
- **Placeholder community boards:** 24 of 140 DCAS energy projects (`ACE…`, `SOLAR…`) list "Brooklyn 01" whatever the site, and the FY26 energy projects (`EO26-…`) list "<borough> 01". Board-based checks and Tier D placements for these programs are unreliable.
- **Engine 326:** FacDB places it in Queens 11, while the project lists Queens 08.
- **Errors in source data:** `pipeline/source_errors.csv` lists every suspected error found so far, with evidence: Tier A points in the wrong place, wrong borough fields, placeholder points (an agency office or one Rikers point standing in for specific sites), and conflicts not yet settled. Most are same-name mix-ups in CPDB (Marcus Garvey Park matched to the Marcus Garvey houses; three projects matched to a Parks property named just "Plaza"). The list could be reported to DCP and Parks. The `unclear` rows (Haitian Studies Institute, Aaron Davis Hall, several borough conflicts) need another source.
- **DSNY garages with two candidate sites:** `S248-423` ($531M Bronx 9/10/11 Garage Replacement) is placed at the existing garage; FacDB also lists a "BRONX DISTRICT 9,10,11 SITE" 700 m south. FacDB gives the new Brooklyn 3 garage two locations (BKN03G / "FUTURE BROOKLYN 3 DIST GARAGE" and "BROOKLYN 3 GARAGE", 2.6 km apart), and CPDB uses the second for `S186-224`.
- **`C11421STC`:** a $433M program-management contract for the borough-based jails. It is currently unplaced. One option is to attribute it to the four jail sites.
- **`P-4SUNRSE` ("Sunrise Stables Acquisition"):** this is matched to Sunrise Playground, which may be wrong. It needs verification before it goes into the golden set.

### Multi-site projects: per-site budget shares
Some projects have several known sites. Each project gets one location, its most central site, plus `spread_m`, the distance from that site to the farthest one. The `project_sites` table keeps every site, with a share of the budget.
- **Shares:** split equally across sites, and labelled as estimates (`share_method = 'equal'`). Shares sum to the project budget, so non-geographic totals are unchanged.
- **Sources of sites:**
  - CPDB points, Parks tracker and DOT/DEP intersections with several points: 104 projects, $3.75B. The median spread is about 4 km; 71 projects spread over 2 km.
  - Titles naming units in different buildings ("26th, 42nd & 46th Precincts"), which are currently left unplaced.
  - At district level, projects listing several community districts (71 projects, $1.2B), split across those districts.
- **Kept alongside:** the single representative point and `spread_m`, so the map and existing metrics still work.
- **Reported in `docs/profile.md`:**
  - money split, and its share of the total budget, by source and tier
  - sites per project (median and maximum)
  - distance from each site to the project's single point (median and 90th percentile)
  - how district and heatmap totals change when shares replace the single point
- **Known proportions:** the Parks capital tracker (`4hcv-tc5r`) publishes `TotalFunding` for each tracker entry. In 37 FMS IDs with several entries the amounts differ by site (P-6POGC15: four pools, $54k to $220k); in 154 others every entry repeats the project total. The entries' sum is not the FMS budget (median 0.90×, mostly 0.56–1.31× in the 22 current projects), so use them as proportions (`share_method = 'source_proportion'`). These projects also measure how far an equal split is from the real one. Loaded as `loc_parks_tracker.total_funding`. DOT/DEP intersection costs and CPDB amounts repeat per project, so they give no split.
- **Better shares later** (unverified ideas): weight sites by lot or floor area from PLUTO, by line length for street work, or by per-site contract amounts if a contract dataset links contracts to sites.
- **Timing:** with the export step, since it changes what the site reads. The multi-unit title parsing can come earlier.

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

### Capital programs outside the city's project data
Several public bodies build in the city but run their own capital programs, so their work is absent or only partly present in the four core datasets. Each would be a separate layer with its own keys and location work.

| Body | What it builds | Why it is missing here | Candidate source |
|---|---|---|---|
| School Construction Authority (SCA) | public schools for the Department of Education | its own five-year capital plan; Education in this data is almost all CUNY | NYC Open Data: "Capital Project Schedules and Budgets" (`2xh6-psuq`), "Active Projects Under Construction" (`8586-3zfm`), "Five Year Plan Summary by Capital Category" (`24nr-gahi`) |
| Housing Preservation and Development (HPD) | affordable housing, through loans and subsidies to private and nonprofit developers | not city-managed construction, so no FMS projects with phases and schedules | "Affordable Housing Production by Project" (`hq68-rnsi`) and "by Building" (`hg8x-zxpr`): units with BBLs, not project budgets |
| NYCHA | repairs and replacement in public housing | a separate public authority funded by federal HUD capital grants, city and state money | none found on NYC Open Data; NYCHA publishes its capital plan as documents (unverified) |
| MTA | transit | see below | see below |

Others in a similar position, to be assessed (unverified):
- **Port Authority of NY & NJ:** airports, PATH, bridges and tunnels; a bistate capital plan.
- **NYC Housing Development Corporation:** housing finance alongside HPD.
- **State public benefit corporations in the city:** Battery Park City Authority, Hudson River Park Trust, Roosevelt Island Operating Corporation.
- **City-affiliated corporations:** Brooklyn Navy Yard, Trust for Governors Island and Brooklyn Bridge Park. Their city capital often appears as EDC projects here, but their own spending does not.
- **CUNY senior colleges:** largely state-funded and often built by DASNY, so CUNY appears here only in part.
- **NYC Health + Hospitals:** present (HHC), but its federal and FEMA-funded recovery work may run outside the city capital budget.

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
- **Golden set:** `tests/golden_locations.csv` has 50 rows; keep adding verified placements and found mistakes, prioritising Tier B placements verified against an independent source.
- **Data checks in CI:** these need the built database, so they run locally. A scheduled job that runs the full pipeline would move them to CI.
- **Frontend tests:** Vitest component tests and a Playwright smoke test of the map, once `web/` exists.
- **End-to-end fixture test:** the full pipeline on a small offline fixture dataset. Low priority, because the data checks cover most of the same risk.

# Future plans

Ideas agreed in principle but not yet scheduled. Current work lives in commits and `docs/profile.md`.

## New data domains

### MTA capital program (state level)
- Candidate source: "MTA Capital Dashboard Project Locations" (`wcsa-vkhf`), which has latitude/longitude. Not yet checked for keys or coverage.
- The state portal (data.ny.gov) uses the same Socrata API, so `pipeline/socrata.py` should work with a different base URL.
- Open question: MTA projects have no FMS ID. Do they appear as a separate layer or a separate view?

### Private development (e.g. supertall progress)
- Candidate sources: DOB job filings and permits (stories, height, status), Certificates of Occupancy, and the DCP Housing Database. All carry BBL/BIN, so they geocode well.
- This is a different model from capital projects: no city budget or variance, only milestones (filed, permitted, under construction, completed). Plan it as its own layer and schema rather than forcing it into capital-project tables.

## Location enrichment beyond the current step
- **Network programs** (resurfacing, pedestrian ramps, signals, real-time signs and similar):
  - Look for operational datasets that show where the work happens, such as DOT in-house resurfacing segments (`ffaf-8mrv`, which has WKT geometry).
  - These link to a program, not to an FMS ID, so show them as program overlays and never as project pins.
- **Out-of-NYC water supply projects** (DEP: Kensico, Hillview, Catskill/Delaware systems):
  - Near facilities such as Hillview and Kensico in Westchester: extend the map extent.
  - Distant facilities such as the Catskill and Delaware reservoirs: show an edge-of-map marker pointing in their direction.
- **Large named "Citywide" projects** (bridges, BQE, coastal resiliency, ferry landings): place them by name through a gazetteer or Geoclient, and prioritise by budget.

## Pipeline hygiene
- Refresh reference layers (FacDB, Parks Properties, district boundaries) on their own, slower schedule.

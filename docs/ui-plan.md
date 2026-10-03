# Frontend design

The site is a static React (Vite) app with no backend. It reads Parquet/JSON files exported by the pipeline. Detailed design and the `web/` build have not started.

## Views
1. **Map with heatmaps.** Projects drawn as points, lines and footprints, with heatmap layers driven by the same filters.
2. **Agency variance leaderboard.** Agencies ranked by signed budget variance and signed schedule variance.
3. **Spend progress.** Budget against spend to date, by phase. This highlights projects in construction with little spending, and projects in close-out that are over budget.
4. **Search** across every view: project title, FMS ID and PID, agency, facility or place name (`matched_to`), street, neighborhood, community district and borough. Results jump to the project on the map, or list it with its tier when it has no point. Search runs in the browser over the exported data.
5. **Filters shared by every view:**
   - managing and sponsor agency
   - theme and subtheme (see "Themes")
   - phase group
   - borough and community district
   - budget size band
   - whether the project has a schedule
   - location precision (tier)
   - snapshot date

Candidate later views:
- a project detail timeline (forecast completion across snapshots, delay reasons, budget history)
- a breakdown of delay reasons
- city vs non-city funding by fiscal year

## Map display rules

### By location tier
- **Tier A:** solid markers, lines or footprints.
- **Tier B:** visibly approximate (hollow or faded markers), with a "location approximate" note. Measured precision: median error 21 m; about 71% within 100 m, 86% within 500 m and 90% within 1 km. These figures come from Tier B validation in `docs/profile.md`. They are measured in-sample, so they likely overstate precision on unvalidated projects.
- **Tiers C, D and E** (neighborhood, district and borough centroids): never drawn as pins, and never fed into point heatmaps, where they would stack into false hot spots at their centres. Shown instead as shading on neighborhood, district or borough areas beneath the heat layer.
- **Unplaced** (Citywide; about 10% of projects and 14% of budget): a separate list beside the map.

### Special cases
- **Outside NYC:** sites within 30 km of the city (Kensico, Hillview) extend the map extent. More distant reservoirs and aqueducts get edge-of-map markers pointing toward them.
- **Multi-site projects:** Tier A projects with `spread_m` over 2 km show their individual points, not a single averaged pin. For street sources, `spread_m` is the line length instead.
- **Disputed sources:** `project_locations.source_flag` marks placements affected by a known source error (`pipeline/source_errors.csv`). `point_disputed`: "official location disputed" with the evidence. `borough_field_wrong`: "the listed borough appears wrong". `official_point_rejected`: "the official location was rejected as an error; shown at <tier> instead". Notes link to the evidence rather than hiding the project.
- **Coverage disclosure:** the map states its coverage, e.g. "map shows X% of projects / Y% of budget at point level".

## Totals and location precision
- **Non-geographic totals** (agency, citywide, leaderboard, spend progress) count every project; location tier is irrelevant to them.
- **Geographic totals** count only projects located at least as precisely as the area being summed:

| Area | Projects counted |
|---|---|
| Borough | Every project with a borough |
| Community district | Tiers A and B by point, Tier C when the neighborhood lies within one district, plus Tier D. A Tier D project's district comes from the official `community_board` field, so it is exact at district level. E is never counted in any district. |
| Map viewport, radius or heatmap | Tier A. Tier B may be included, labelled approximate. C, D and E are never counted. |

**Multi-site projects:** where a project's sites are known, geographic totals count each site's share of the budget rather than the whole budget at the averaged point. Shares are an equal split, shown as "estimated split across N sites". See "Multi-site projects" in `docs/future-plans.md`.

## Money and variance
- **Deduplicate by FMS ID** before summing budgets: `project_budget_schedule` repeats an FMS ID once per linked PID.
- **Report variance signed.** Variance is the change since the previous report: positive means a budget increase or a later forecast completion.
- **Clamp outliers:** about ±365,000-day schedule variances are data-entry errors (forecast dates in the year 3026).

## Funding and programs
- **City vs non-city money:** each project carries `budget_city` and `budget_non_city`, and `funding.json` gives both per fiscal year (`budget_spend_by_fy`). Non-city money (federal, state, private) is about 6% of the current budget. For 37 projects one managing agency's record has no funding rows, so their split covers part of the budget.
- **Programs:** the manifest's `programs` registry lists every capital program the site shows. The site treats each as a layer with its own files and an adapter to the common project fields, so other programs (MTA, SCA, state) can be added without changing the views.

## Phase groups
`current_phase` has 60 raw spellings, rolled up in `pipeline/phase_groups.csv` after dropping case and punctuation ('(On-Hold)', '(On-hold)' and '(On Hold)' are one value):

| Group | Raw phases |
|---|---|
| Active | Pre-Design, Design, Construction Procurement, Construction, Close-out; also their bracketed forms ('(Pre-Design)'), which are the same phases without a reported schedule (`has_schedule` says which) |
| Done | (Completed) |
| Stalled | (On-hold), (Inactive), (Not Fully Funded), (Fundraising) |
| Ended early | (Cancelled), (Terminated), (Withdrawn), (Defaulted), (Defunded), (Funding Withdrawn), (Rescinded) |
| Not started | (Pending), (Initiation) |
| Not a discrete project | (Lump Sum), (Requirements Contract), (Job Order Contract), (Pass-Through Fund), (Holding Code), (Equipment), (IT Project), (Consultant Services), (Funding Agreement), (Capitally Ineligible) and similar |
| Partner-managed | (Partner-managed): run by a cultural institution, nonprofit or other partner, with no city phase |
| Property | land and real estate purchases, leases |
| Moved or renamed | (Transferred), (FMSID Changed), (Project Renamed) |

## Themes
`pipeline/themes.csv` and `pipeline/themes.py` give every project a theme and, where meaningful, a subtheme. The first matching rule decides the theme:
1. a specific `ten_year_plan_category` ('WATER QUALITY MANDATES', 'FAIR BRIDGES');
2. the sponsor agency, or an agency prefix in the title ('NYPD - ...');
3. the capital budget line that pays for the work ('LQ' Queens Library, 'SE' sewers, 'PV' cultural institutions);
4. the managing agency (DDC builds for others and never decides; DCAS only as a last resort).

The subtheme comes from the first rule that agrees on the theme and names one.

| Theme | Subthemes |
|---|---|
| Transportation | Bridges; Streets and sidewalks; Signals and lighting; Ferries |
| Water and sewer | Water supply; Water mains and sewers; Treatment and water quality |
| Public safety and justice | Police; Fire and EMS; Courts; Jails and corrections |
| Health | Hospitals; Public health |
| Libraries and culture | Libraries; Culture |
| Social services | Homeless shelters; Children and families; Older adults; Benefits and social services |
| Parks; Economic development and waterfront; Government buildings and operations; Education; Sanitation; Housing | none |

Education is almost entirely CUNY: public schools are built by the School Construction Authority, which has its own capital plan and datasets. Housing is small for a similar reason: HPD's capital mostly funds private and nonprofit developers, and NYCHA runs its own capital program.

## Open questions
- **Leaderboard attribution:** budget variance is at FMS level and schedule variance at PID level, so they may need to be two separate rankings.
- **Leaderboard normalisation:** normalise by portfolio size so the largest agencies (DDC, DEP) don't dominate.
- **Heatmap weighting:** by project count, by budget, or a toggle.
- **Snapshot comparisons:** latest snapshot only, or change since a chosen earlier snapshot.

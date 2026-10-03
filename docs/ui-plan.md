# Frontend design

The site is a static React (Vite) app with no backend. It reads Parquet/JSON files exported by the pipeline. Detailed design and the `web/` build have not started.

## Views
1. **Map with heatmaps.** Projects drawn as points, lines and footprints, with heatmap layers driven by the same filters.
2. **Agency variance leaderboard.** Agencies ranked by signed budget variance and signed schedule variance.
3. **Spend progress.** Budget against spend to date, by phase. This highlights projects in construction with little spending, and projects in close-out that are over budget.
4. **Filters shared by every view:**
   - managing and sponsor agency
   - theme (rolled up from `ten_year_plan_category`)
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

## Phase groups
`current_phase` has 36 raw values, rolled up into these groups (case and spelling variants, e.g. "Construction procurement", are normalised first):

| Group | Raw phases |
|---|---|
| Active | Pre-Design, Design, Construction Procurement, Construction, Close-out. Only these have schedules. |
| Done | (Completed) |
| Stalled | (On-hold), (Inactive) |
| Ended early | (Cancelled), (Terminated), (Withdrawn), (Defaulted) |
| Not a discrete project | (Lump Sum), (Requirements Contract), (Job Order Contract), (Pass-Through Fund), (Holding Code), (Equipment), (IT Project) and similar |
| Not started | (Pending), (Initiation) |

## Themes
`ten_year_plan_category` has 122 values. An explicit mapping rolls them up into about 10 themes: transport, water and sewer, parks, health, education, public safety, housing, culture, government facilities, and other. The raw categories are not exposed as a filter.

## Open questions
- **Leaderboard attribution:** budget variance is at FMS level and schedule variance at PID level, so they may need to be two separate rankings.
- **Leaderboard normalisation:** normalise by portfolio size so the largest agencies (DDC, DEP) don't dominate.
- **Heatmap weighting:** by project count, by budget, or a toggle.
- **Snapshot comparisons:** latest snapshot only, or change since a chosen earlier snapshot.

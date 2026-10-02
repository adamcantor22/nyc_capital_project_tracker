# UI plan (Step 3)

Status: views chosen by the user on 2026-10-02. Detailed design and the `web/` build have not started.
The stack is a static React (Vite) site reading Parquet/JSON exported by the pipeline (see CLAUDE.md).

## Chosen views
1. **Map with heatmaps.** Projects as points, lines and footprints, plus heatmap layers driven by the same filters.
2. **Agency variance leaderboard.** Agencies ranked by signed budget variance and signed schedule variance.
3. **Spend progress.** Budget vs spend-to-date, e.g. by phase, to surface projects in construction with low spend or in close-out with overruns.
4. **Filters across all views:**
   - managing and sponsor agency
   - theme (rolled-up `ten_year_plan_category`)
   - phase group
   - borough and community district
   - budget size band
   - "has a schedule"
   - location precision (tier)
   - snapshot date

Also suggested, not yet chosen: a project detail timeline (forecast completion across snapshots, delay reasons, budget history), a delay-reason breakdown, and city vs non-city funding by fiscal year.

## Design rules agreed so far

### Location tiers on the map
- **Tier A:** solid markers, lines or footprints.
- **Tier B:** visibly approximate (hollow or faded markers), with a "location approximate" note.
  - Measured precision, in-sample (`docs/profile.md`, Tier B validation): median error about 27 m; about 70% within 100 m, 86% within 500 m and 89% within 1 km.
  - A spot-check of projects outside the validation set ran lower (about 75% before later fixes).
- **Tiers C and C2** (district or borough centroid): never drawn as pins, and never fed into point heatmaps, because they would stack into false hot spots at district and borough centres. Show them as shading on district or borough areas under the heat layer.
- **Unplaced** (Citywide, about 10% of projects and 14% of budget): a separate list beside the map.
- **Outside NYC:** Kensico (near) extends the map extent; the far upstate reservoirs and aqueducts get edge-of-map markers pointing toward them. `docs/profile.md` has the near/far split.
- **Multi-site Tier A projects** with `spread_m` over 2 km: draw the individual points, or flag them, rather than one averaged pin. For street sources `spread_m` holds the line length instead.
- **Show coverage honestly**, e.g. "map shows X% of projects / Y% of budget at point level".

### Totals and location precision
- **Non-geographic totals** (agency, citywide, leaderboard, spend progress) count every project; location tier is irrelevant to them.
- **Geographic totals** count only projects located at least as precisely as the area being summed:
  - **By borough:** every project with a borough.
  - **By community district:** Tiers A and B by point, plus Tier C. A Tier C project's district comes from the official `community_board` field, so it is exact at district level. C2 is not counted in any district.
  - **Smaller or arbitrary areas** (map viewport, radius, heatmap intensity): Tier A for exact figures. Tier B may be included but must be labelled approximate. C and C2 are never counted.

### Money and variance
- **Deduplicate by FMS ID** before summing budgets. `project_budget_schedule` repeats an FMS ID once per linked PID.
- **Report variance signed.** Clamp the junk schedule-variance outliers (about ±365,000 days).
- **Leaderboard, still to confirm with the user:**
  - Budget variance at FMS level and schedule variance at PID level, shown as two separate rankings.
  - Normalise by portfolio size so DDC and DEP don't dominate.

### Phase groups
`current_phase` has 36 raw values. Roll them up into these groups:
- **Active:** Pre-Design, Design, Construction Procurement, Construction, Close-out. Only these have schedules.
- **Done:** (Completed).
- **Stalled:** (On-hold), (Inactive).
- **Ended early:** (Cancelled), (Terminated), (Withdrawn), (Defaulted).
- **Not a discrete project:** (Lump Sum), (Requirements Contract), (Job Order Contract), (Pass-Through Fund), (Holding Code), (Equipment), (IT Project) and similar.
- **Not started:** (Pending), (Initiation).

Normalise case and spelling variants, e.g. 'Construction procurement'.

### Themes
Roll `ten_year_plan_category` (122 values) up into about 10 themes: transport, water/sewer, parks, health, education, public safety, housing, culture, government facilities, other. Map it explicitly; don't use the raw categories as a filter.

## Open questions
- Leaderboard attribution and normalisation (see above).
- Heatmap weighting: by project count, by budget, or user-selectable.
- Which snapshot comparisons to expose: latest only, or change since a chosen earlier snapshot.

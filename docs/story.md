# The story

A scrolling story opens the site: text cards over a pinned map, each card a saved map state computed from the data, ending with the full map unlocked (future-plans, Sequence, step 9). This document holds the story's approach, the rules every card follows and the candidate cards with what each still needs. Figures quoted here were measured on the May 2026 city snapshot, SCA's August 2026 list and the MTA's latest quarterly load; the cards will compute them from the data (`story.py`, to be built), so they refresh with each update.

## Approach

- **Explainer first.** The story is a tour of what the city and its authorities are building, where, and how it is going. Delays and budget changes are part of that picture, not the headline.
- **All three programs.** The city's capital program, the School Construction Authority (SCA) and the MTA appear side by side. SCA is close to a city agency (the city funds most of its program); the MTA is a state authority with its own funding. Each program's own rules are named wherever they differ.
- **Lasting cards.** A card states something that adding a new data source will not overturn. Coverage notes (what the site does not include) belong on the site's about page, not in the story.
- **Context, not judgement.** Size is not wrongdoing: the MTA's program is large because it carries whole rail systems and fleets, and the cards say so. Interpretation cites published analysis (State and City Comptrollers, IBO, CBC, research groups) where it exists.

## Rules for every card

- Figures are computed the way the site counts: current projects by default, each program's own money measure, the location-precision rules for any geographic figure, and SCA projects that are the same work as a city record counted once.
- Programs are shown side by side, never added into one total, because they measure money differently (city FMS commitments, SCA's final estimate of actual costs, the MTA's current budget).
- "Late" is measured by each program's own rule and never compared across programs.
- Budget change is a signed change in commitments or allocations, not cost growth alone.
- Amounts are nominal until inflation adjustment is built (future-plans, Inflation); comparisons across years then show constant dollars with the base year and index named.
- Every geographic figure states the share of money it counts.
- Display names are written as readers know them ("The Bronx"), and every acronym is spelled out on first use and in a glossary.
- Charts are interactive only where interaction adds something: a time scrubber where the data has a time dimension, a timelapse where change over time is the point, hover or tap details instead of printed labels that compete with the marks, and linked map and chart where a selection means something in both.

## Candidate cards

The first round (October 2026) reviewed 40 candidate findings; most continue to a second, more detailed round (data builds, checks against published analysis, interactive charts) before the arc is chosen.

### Scale
- **Three builders.** Projects and money per program, side by side, framed so the MTA's size reads as what it builds.
- **The biggest projects.** The largest unfinished projects. Needs: a clearer account of how each agency slices work into projects (a building, an equipment order, a citywide program, or one program split into many projects), since that decides what "largest" means; project families (future-plans) would let a group be ranked as one.
- **Concentration.** One card for all three programs: the share of money in the largest projects, shown as shares and in dollars.
- **Physical work and overhead.** About 1% of city and 4% of MTA money is overhead. Needs: a recheck of the classification for overhead work listed at a facility's address.
- **Who builds.** Money by managing agency, with every agency name spelled out.

### What
- **Themes.** Money by theme across programs. Needs: the theme scheme reworked (several design rounds) before it is shown.
- **The borough-based jails.** About $16.4B for the four jails replacing Rikers Island; interpretation from cited analysis, including what comparable sums could fund, alongside the legal requirement to close Rikers.
- **The places people use.** Libraries, firehouses, precincts, parks, cultural institutions, shelters, senior centers and schools: many small projects.
- **The work nobody sees.** Water and sewer work and the upstate water supply.

### Where
- **Per resident.** One card in two steps: all money per resident by borough, district and neighborhood first (where large facilities that serve the whole city sit), then by the area the work serves. Each project is classed local, regional or citywide in the City Planning Department's Statement of Needs terms (`pipeline/serving.py`): local work counts per resident by district and neighborhood, regional work by borough, citywide work only in the citywide figure. MTA work mostly outside the five boroughs (LIRR and Metro-North in the suburbs) is classed outside the city and counts in no per-resident figure; the city's own upstate water supply works serve city residents, so they stay citywide. A class is what the work serves by its nature; where it counts is also limited by how precisely it is located, so an unplaced program of local work (signal installation citywide) counts only citywide. Some classes rest on official evidence beyond the Statement: DHS shelters people in their home boroughs and DOC's borough-based jails hold people near their borough's courts, so both are regional. Subway station and line work is classed by where its morning riders live, measured from MTA's origin-destination estimate, so Gun Hill Rd and Grand Central can differ. Needs: the classification reviewed (round 2: thresholds for the ridership classes, culture, bridges, the remaining government buildings); district totals recomputed under the location rules (Tiers A, B and D, and C where the neighborhood lies in one district, multi-site projects by site share) before any figure is shown; a per-resident area measure; maps shaded by value.
- **How much can be placed.** The share of money at a known site, known only to an area, or citywide; with a wider question on how precise even official points are (a facility's point against where the work happens).

- **Shapes in the data.** Lines and clusters that points trace on the map: rail lines, the Broadway malls on the Upper West Side (one $0.2M Parks repair project, P-307BWYM, drawn as 30 sites from CPDB's footprint), street resurfacing and sewer lining contracts with over 100 sites each, and families of officially separate projects along one corridor (DOT's bridges over Amtrak's 30th Street Branch, West 33rd to 40th Streets: eight current projects, about $630M, continuing north to the West 79th Street bridges and the Riverside Park overbuild). They show where work follows a corridor, and also how one small multi-site project can look as large as a major one, so the card pairs the shape with the money behind it.

### Progress
- **Where the work stands.** Each program's unfinished money by its own phases.
- **Finishing soon.** Projects expected to finish by the end of 2027, for "what near me is almost done?".
- **Finished recently.** Projects that finished between recent reports, across programs. Needs: completions detected from changes between snapshots rather than each program's listing practice.
- **Known schedules.** Only about half of city projects give a dated finish; budget spent to date may stand in where no schedule exists.

### Schedules
- **Running late.** Per program, by its own rule. City projects are measured against OMB's original finish where its Capital Project Detail Data (2019-2023) holds one: 91% are later, by a median of about 50 months. Needs: a clearer chart; OMB's stated delay reasons by edition.
- **Why sources are hard to compare.** How each source records dates and schedules, and why one figure cannot cover all three.

### Money over time
- **City budgets against their originals.** In constant construction dollars the change shrinks from +$51.5B to +$17.1B. Needs: growth split by the phase a project was in when its original was recorded (an original set during scope or design grows as construction money is added, as with West 35th Street over the 30th Street Branch, $2.7M to $78.5M; one set in construction is closer to an overrun), from the snapshots' phases and OMB's 2019-2023 milestones.
- **Lump sums and the oldest projects.** Needs: where moved money went, traced approximately (the city's financial system does not link holding codes to the projects funded from them), shown as a timelapse.
- **MTA mega projects.** Budgets since 2020 on the dashboard and, from the MTA's funding plans, since 2008 (East Side Access from $1.74B in 2008 to $10.67B by 2024). Reasons for growth from cited sources.
- **How MTA plans change.** Plan totals at each approval, and where amended money moved.
- **School project costs.** SCA's estimates since each project was first seen. Needs: the cost change in the export.

### Who pays
- **Who pays for the city's work.** The city funds about 94% of its own capital work; federal money and the exposure to federal cuts.
- **Where federal money goes.** Federal share by theme, without labels that compete with bar length.
- **How funding sources change.** Federal and state shares across the planning database's releases, 2024 on.

### What is no longer published
- **What the city stopped publishing.** The City Charter (section 219(d), as amended by Local Law 35 of 2021) requires capital project detail data reports, with schedules and explanations of delays, three times a year in machine-readable form. OMB's last edition is October 2023; since January 2024 the Capital Projects Dashboard has been treated as the replacement, and the City Comptroller found it holds about 47% of FMS IDs and gives reasons for about half of delayed projects. The card shows what the 2019-2023 editions reveal (original schedules and delay reasons) that later data cannot, citing the Charter and the Comptroller rather than asserting a violation.

### New sources, in the second round
- OMB's Capital Project Detail Data (2019–2023): baselines and delay reasons.
- Climate Budgeting: each project's climate ratings.
- Community board budget requests: what neighborhoods asked for and what the city answered.
- City Council capital awards: what each Council member funded.
- Planned against actual commitments.
- What a taxpayer paid into which projects, by income bracket (a modelled estimate).

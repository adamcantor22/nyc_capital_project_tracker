---
version: 1
slug: "web-src-app-tsx"
primary_target: "web/src/App.tsx"
related_targets: []
---

# Map shell (web/src/App.tsx)

Mode: Operate. Residents first (often on a phone), with analyst depth one step away. Task: find projects near an address or in an area, read status (phase, budget, spend, signed change, location precision) at a glance. Real data only (data/export, schema v2). Code-led build.

Scope: the map with tier-aware layers, search, a legend-driven filter bar, a project detail panel, the unplaced list, a coverage note, outside-NYC markers, responsive. Leaderboard and spend views come later on this system. Anti-goals: a generic SaaS dashboard, hiding uncertainty, analyst density up front, joylessness, vintage costume.

Open: site name, heatmap weighting, leaderboard normalization.

## Direction contract

THESIS: The city as a hand-tinted Sanborn atlas sheet: watercolour tints say what a project is, engraved hatching says how surely it is placed. It refuses the open-data dashboard (grey panel, blue pins, KPI tiles).

OWN-WORLD: Cool white sheet, a slate atlas-cloth binding rail, ink-black outlines. Twelve watercolour tints for themes (brick pink, frame yellow, stone blue, sage, ochre…). Precision is a hatch-density ramp: A is a solid tint, B is a hatched tint with an ink ring, C–E are hatched area washes and never pins. Labels are lettered in condensed caps like atlas street names; the UI is set in one workhorse sans with tabular figures.

STORY: Residents see what is being built around them, how much of it is known precisely, and what changed in the latest report; then they open a project for its budget, schedule and evidence.

FIRST VIEWPORT: Full-bleed map; on desktop a left binding rail carries search at the top, then the live legend key (theme swatches on a rail sized by budget share; precision swatches A–E) and the in-view list. A coverage line sits under the legend. On mobile the search floats over the map and the legend and list live in a bottom sheet.

FORM: Sanborn Atlas, candidate 3 of 7; seed key 6b6c6574. Signature interaction: the legend key is the filter. Tapping a swatch toggles it, and hovering lights its marks. Raises: a lit change mark until opened; a theme rail sized by budget; schedule bars drawn to exact duration.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance

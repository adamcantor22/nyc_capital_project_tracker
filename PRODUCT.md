# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

Static React (Vite) site with no backend, in `web/`. The map uses MapLibre GL with keyless vector tiles (OpenFreeMap or Protomaps). The site reads the JSON and GeoJSON written by `pipeline/export.py`. It is hosted on GitHub Pages; the export is fetched at build time from a GitHub Release asset.

## Users

- **Primary: New York City residents** who want to know what the city is building near them or across the city, how far along it is, and whether it is late or over budget. They arrive curious, not expert, often on a phone, and need plain language and a map-first entry.
- **Also served:** journalists and civic analysts, who need filters, variance rankings, project IDs and links back to source records; and portfolio reviewers, who look for method transparency and craft. Their depth stays reachable without crowding residents.

## Product Purpose

The site makes the city's capital projects legible. That is about 5,600 current projects and $160B in budget, plus every project reported since May 2023. It shows where each project is, what it costs, how money and schedules have changed across snapshots, and how precisely its location is known. Success means a resident can find the projects that matter to them and understand their status without reading a spreadsheet, and an analyst can trust and trace every number.

## Positioning

The city publishes these datasets without coordinates. This project builds locations only from official sources, measures each method's accuracy, and shows that precision openly. Approximate placements are labelled as approximate, and coarse locations are never drawn as pins. No scraped or hand-entered data is used. Money totals are deduplicated per FMS ID and managing agency.

## Operating Context

- Data refreshes three times a year (January, May, September snapshots). The site shows the latest snapshot and history across snapshots.
- It covers every project ever reported, with status current or dropped.
- Location tiers (A official point through E borough centroid, plus Unplaced) govern display and totals; the rules are in `docs/ui-plan.md`.
- Search, filters and totals run in the browser.

## Capabilities and Constraints

- **Views:** a map with heatmaps, search, an agency variance leaderboard, spend progress, and shared filters (`docs/ui-plan.md`).
- **Variance is always signed:** positive means a budget increase or a later completion.
- **Modular by design:** the site must accept other capital programs (MTA, SCA, state, NYCHA) as separate layers, the city / non-city funding split, and later budget context, without rewrites.
- **Undecided:** the site's name (use a working title), the heatmap weighting, the leaderboard normalization, and snapshot comparisons (listed in `docs/ui-plan.md`).

## Evidence on Hand

- Real data in `data/export/`: projects, schedules, budget history, sites, lines, footprints and area boundaries. Validation metrics are in `docs/profile.md`.
- There are no testimonials, press, users or partnerships, so none may be invented. The site is an independent project, not an official city product, and must not imply city endorsement.

## Product Principles

1. **Honest precision.** Every location shows how it was derived and how precise it is. Never imply more precision than the data has.
2. **Official sources, traceable numbers.** Every figure can be traced to a dataset and a project ID.
3. **Residents first, depth on demand.** Plain language and the map lead; analyst detail is one step away.
4. **Signed, comparable change.** Show direction and size of budget and schedule changes, and normalize where size would mislead.
5. **Built to grow.** New programs and funding dimensions slot in as data, not as rewrites.

## Accessibility & Inclusion

Target WCAG 2.2 AA: contrast, full keyboard use, visible focus, reduced-motion support. The map has a list or table alternative, so every project is reachable without the map.

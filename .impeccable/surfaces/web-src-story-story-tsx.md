---
version: 1
slug: "web-src-story-story-tsx"
primary_target: "web/src/story/Story.tsx"
related_targets: []
---

# Story (web/src/story/Story.tsx)

Mode: Read. A scrolling story at /story/: text plates over a pinned map, each plate a computed map state, ending in the map tool. Readers are residents first (often on a phone), then journalists and analysts. Built inside the Sanborn Atlas world of the map shell, pushed further on the story (larger lettering, plate apparatus). Template plates first: Three builders (text-led) and Per resident (map-led). Figures are computed in the browser from data/export; area-served figures are labelled estimates. Programs are shown side by side, never added. Anti-goals: an NYT scrollytelling clone with grey cards, KPI tiles, a hero metric, vintage costume, analyst density up front.

Open: the remaining plates (after the round 2 review), the first-visit rule (story on first visit, map after), the site name.

## Direction contract

THESIS: The story is an atlas you read plate by plate: a key sheet shows where every plate falls and lights the one you are on, while the pinned map sheet turns to that plate. It refuses the scrollytelling default of anonymous floating cards over a map.

OWN-WORLD: The map shell's world pushed further: cool white sheet, slate binding, ink outlines, gilt for "you are here", watercolour tints. Plate titles lettered big in condensed caps (Archivo at its narrowest width); the reading column in Archivo at normal width, 17px, 66ch. The key sheet is a small inked index: the city's outline with the current plate's extent drawn as a numbered sheet, and the plates as numbered sheet tabs. Published figures set solid; estimates set over a hatch, the same hatch that marks approximate places on the map.

STORY: The reader learns who builds what (three programs, side by side), then where the money sits per resident, first by where the work is, then by whom it serves; then opens the map to look near them.

FIRST VIEWPORT: Desktop: left column (the binding width, about 30rem) on the white sheet: key sheet at top (city outline with Plate 1's frame, plate tabs 1, 2, Map), then Plate 1's lettered title "Three builders", its opening paragraph and figure; the map sheet fills the rest, showing every placed project tinted by program. "Skip to the map" sits in the key sheet. Phone: map full screen, key as a strip of plate tabs on top, plates scroll up from the bottom over the map.

FORM: Key sheet, position 3 of 7 on the ranked structure list; seed key e4a301ca. Signature interaction: scrolling lights the current plate on the key sheet and turns the map to that plate (camera and layers crossfade); a gilt flag marks the plate where the reader stopped and resumes there on return. Raises: estimates in hatched type (from the provenance ribbon), the resume flag (from the cutting bench).

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance

# Catalog Horizontal Filter Bar

**Date:** 2026-04-15
**Status:** Ready for planning

## What We're Building

Replace the vertical sidebar filter panel on the Katalog page with a horizontal filter bar positioned above the title grid. The bar shows category labels (e.g. "Platforma", "Zanr") in a single scrollable row. On hover, a dropdown opens with selectable pills (for small dimensions) or an autocomplete search (for large dimensions like actors).

Additionally, expand the filterable dimensions to include all crew roles (actors, directors, screenwriters, cinematographers, composers) that were not in the original sidebar.

## Why This Approach

- Horizontal bar uses vertical space more efficiently — the full viewport width is available for the title grid
- Collapsed-by-default dropdowns reduce visual clutter vs. the always-visible sidebar
- Hover interaction is fast and frictionless on desktop
- Single-row layout scales well with horizontal scroll when categories overflow
- Grouping all crew into one "Tvurci" dropdown avoids bar bloat (5 crew roles would be too many items)

## Key Decisions

### Filter Categories (9 items in bar)

| # | Category | Values | UI Type | Trigger |
|---|----------|--------|---------|---------|
| 1 | Zanr | 21 | Pill checkbox dropdown | Hover |
| 2 | Platforma | 23 | Pill checkbox dropdown | Hover |
| 3 | Krajina | 75 | Pill checkbox dropdown | Hover |
| 4 | Typ | 8 | Pill checkbox dropdown | Hover |
| 5 | Tagy | 2,119 | Autocomplete + pill | Hover |
| 6 | Tvurci | ~70k combined | Autocomplete + role label | Hover |
| 7 | Rok vyroby | range | Dual range slider (from-to) | Hover |
| 8 | Hodnoceni | min threshold | Single range slider (min %) | Hover |
| 9 | Nazev | text search | Search input | Always visible |

### Dropdown Behavior

- **Pill dropdown** (Zanr, Platforma, Krajina, Typ): Grid of pills, click to toggle. Active pills highlighted. Count badge on category label.
- **Autocomplete dropdown** (Tagy, Tvurci): Text input at top, filtered results below. Selected values shown as pills. Tvurci results show role (Herec, Reziser, etc.).
- **Range slider dropdown** (Rok, Hodnoceni): Rok = dual range slider (from-to, e.g. 1992-2026) with value labels. Hodnoceni = single range slider (min %, e.g. 60%+) with value label. Both inside dropdown panel.
- **Search** (Nazev): Always-visible text input at the end of the bar, no dropdown.

### Layout

- **Desktop**: Single scrollable row. `display: flex; gap; overflow-x: auto`. Each category is a button-like element. Active filters show count badge.
- **Mobile (<640px)**: Same as current — FAB button + bottom sheet. No horizontal bar.
- **Dropdown position**: Opens below the category button, aligned left. Closes on mouse leave.

### Interaction Model

- **Hover to open** on desktop (no click required)
- Close on mouse leave (with small delay ~150ms to prevent flicker)
- Multiple dropdowns cannot be open simultaneously
- Selected values persist in URL params (existing behavior, no change)

### Tvurci (Crew) Autocomplete

- Single dropdown combining all 5 crew roles
- Search input filters across all crew names
- Results show: `Name (Role)` — e.g. "Brad Pitt (Herec)", "Christopher Nolan (Rezie)"
- Selected crew shown as pills with role prefix
- Data source: needs new combined crew index in JSON export (or client-side merge of existing arrays)

### Data Changes Required

Current `dimensions.json` has: genres, tags, countries, platforms.
Need to add:
- `directors[]` — list of all director names
- `actors[]` — list of all actor names (potentially top N by frequency to avoid 53k items)
- `screenwriters[]`
- `cinematographers[]`
- `composers[]`

Or a combined `crew[]` with `{name, role, count}` entries.

For filtering to work client-side, `titles_index.json` needs crew arrays per title (currently only in `titles_detail.json`). This is a significant data size increase.

### Active Filter Indicators

- Category label shows count badge: "Zanr (3)" when 3 genres selected
- Below the bar (optional): row of "active pill chips" showing all selected values with X to remove
- Clear all button when any filter is active

## Open Questions

_None — all resolved during brainstorm._

## Resolved Questions

1. **Mobile behavior?** — Keep existing bottom sheet, horizontal bar only on desktop
2. **Hover vs click?** — Hover on desktop
3. **Which categories?** — All available dimensions including crew
4. **Crew grouping?** — Single "Tvurci" dropdown with autocomplete, results show role
5. **Layout?** — Single scrollable row
6. **Data impact?** — Need to extend JSON exports with crew data per title

## Scope & Constraints

- The Katalog page component is currently 857 lines — this refactor should split filters into a separate component
- Client-side filtering of 53k actors is not feasible as a full list — need frequency-based top-N or server-side search fallback
- `titles_index.json` is currently 3.3MB — adding crew arrays per title will increase this significantly
- URL param sync must continue working (existing behavior)

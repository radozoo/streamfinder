---
title: "feat: Catalog horizontal filter bar with crew filtering"
type: feat
status: active
date: 2026-04-15
origin: docs/brainstorms/2026-04-15-catalog-horizontal-filter-bar-brainstorm.md
---

# feat: Catalog horizontal filter bar with crew filtering

## Overview

Replace the vertical sidebar filter panel on the Katalog page with a horizontal filter bar above the title grid. Add crew filtering (actors, directors, screenwriters, cinematographers, composers) as a new capability. Implement hover-to-open dropdowns with pill selectors, autocomplete search, and range sliders.

## Problem Statement

The current sidebar takes 220px of horizontal space, reducing the title grid area. Filter options are always visible, creating visual clutter. Crew dimensions (53k actors, 6.5k directors) are available in the database but not exposed in the catalog UI.

## Proposed Solution

A single-row horizontal filter bar with 9 category buttons. Each opens a dropdown on hover:
- **Pill checkboxes**: Žáner (21), Platforma (23), Krajina (75), Typ (8)
- **Autocomplete**: Tagy (2,119), Tvůrci (~69k combined crew)
- **Range sliders**: Rok výroby (dual), Hodnocení (single)
- **Search input**: Název (always visible, no dropdown)

Desktop: hover-to-open dropdowns. Mobile (<640px): existing bottom sheet (with new filters added).

## Key Decisions (from brainstorm)

All decisions below were made during brainstorming (see brainstorm: `docs/brainstorms/2026-04-15-catalog-horizontal-filter-bar-brainstorm.md`):

- Horizontal bar, single scrollable row
- Hover to open on desktop, bottom sheet on mobile
- All dimensions filterable including crew
- Crew grouped into one "Tvůrci" dropdown with autocomplete + role labels
- Range sliders for year and rating (not text inputs)

## Technical Decisions (from SpecFlow analysis)

These resolve open questions identified during spec analysis:

| # | Question | Decision | Rationale |
|---|----------|----------|-----------|
| Q1 | Crew data loading | Lazy-load separate `crew_index.json` | Avoids bloating initial 3.3MB payload; 80%+ users won't filter by crew |
| Q2 | Crew URL params | Repeated params: `?crew=A&crew=B` | Handles commas in names (e.g. "Robert Downey, Jr."); `getAll()` is standard |
| Q3 | Crew filter matching | By name across all roles | User wants "titles with this person" regardless of role |
| Q4 | Hover bridge | Parent wrapper div (trigger + dropdown) | Simplest solution; `mouseenter`/`mouseleave` on wrapper, not individual elements |
| Q5 | Autocomplete pin | Keep open while input focused | Prevents close when mouse leaves during typing |
| Q6 | Mobile parity | Add new filters to bottom sheet | Otherwise mobile users can't modify crew filters set via URL |
| Q7 | Slider crossover | Swap values silently | Lower value always = "from" |
| Q8 | Crew frequency | Show count: "Brad Pitt (Herec, 12)" | Helps assess filter usefulness |
| Q9 | Crew cutoff | 2+ appearances (~26k names) | Cuts 60% of corpus; single-appearance crew unlikely to be searched |
| Q10 | Sort location | Stays outside filter bar as `<select>` | Not a filter; different interaction pattern |

## Implementation Phases

### Phase 1: Data Pipeline — crew_index.json export

Extend the Python exporter to produce a new `crew_index.json` file and add crew IDs to `titles_index.json`.

**Tasks:**
- [ ] Add `crew_index.json` export to `StreamfinderExporter` (`src/csfd_vod/export/streamfinder_exporter.py`)
  - Combined crew lookup: `[{id, name, role, count}]` sorted by count desc
  - Filter to 2+ appearances only (~26k entries)
  - Roles: "herec", "režie", "scénář", "kamera", "hudba"
- [ ] Add per-title crew ID arrays to `titles_index.json`: `crew_ids: number[]`
  - Only include IDs that exist in the crew lookup (2+ appearances)
- [ ] Add crew dimensions to `dimensions.json`: `crew: [{name, role, count}]` (top 50 for facet panel display)
- [ ] Update `_write()` calls in `export()` method to include the new file
- [ ] Measure file sizes before/after (target: crew_index.json < 400KB gzipped)

**Files:**
- `src/csfd_vod/export/streamfinder_exporter.py` — add `_load_crew()`, `_build_crew_index()`, extend `_build_index()`
- `streamfinder/static/data/crew_index.json` — new file

**Acceptance criteria:**
- [ ] `crew_index.json` exported with ~26k entries, < 400KB gzipped
- [ ] `titles_index.json` has `crew_ids[]` per title
- [ ] Re-export produces valid JSON; no key mismatches (apply contract test pattern from `docs/solutions/integration-issues/streamfinder-data-pipeline-frontend-mismatches.md`)

---

### Phase 2: TypeScript types + data loader

Update frontend types and the catalog page data loader for new crew data.

**Tasks:**
- [ ] Extend `TitleIndex` in `src/lib/types.ts`: add `crew_ids: number[]`
- [ ] Add `CrewEntry` type: `{id: number, name: string, role: string, count: number}`
- [ ] Extend `Dimensions` type: add `crew: CrewEntry[]`
- [ ] Update `katalog/+page.ts`: parse new URL params (`crew` via `getAll()`)
- [ ] Add lazy-load function for `crew_index.json` in a new `src/lib/data/crew.ts` module
- [ ] Add `initialCrew` to page data return type

**Files:**
- `streamfinder/src/lib/types.ts`
- `streamfinder/src/routes/katalog/+page.ts`
- `streamfinder/src/lib/data/crew.ts` — new file: `loadCrewIndex()` with cache

**Acceptance criteria:**
- [ ] TypeScript compiles with no errors
- [ ] URL `?crew=Brad+Pitt&crew=Christopher+Nolan` correctly parsed on page load
- [ ] `loadCrewIndex()` fetches and caches crew_index.json on first call

---

### Phase 3: Component extraction — FilterBar shell

Extract filter logic from the 857-line catalog page into reusable components. Build the horizontal bar layout without dropdown content first.

**Tasks:**
- [ ] Create `src/lib/components/FilterBar.svelte` — horizontal bar container
  - Props: `dimensions`, `activeFilters` (counts per category), `onFilterChange`
  - Single flex row with overflow-x: auto
  - 9 category trigger buttons with count badges
  - Hidden on mobile (<640px)
- [ ] Create `src/lib/components/FilterDropdown.svelte` — generic dropdown wrapper
  - Props: `label`, `activeCount`, `children` (snippet)
  - Hover-to-open with 150ms close delay
  - Parent wrapper div for mouse bridge
  - Pin open when child input is focused
  - Keyboard: Enter/Space to toggle, Escape to close
  - ARIA: `aria-expanded`, `aria-haspopup`
  - Position: below trigger, aligned left (flip if near viewport edge)
- [ ] Create `src/lib/components/ActiveFilters.svelte` — chip row below bar
  - Shows all active filter values as removable chips
  - "Zrušit vše" (clear all) button
- [ ] Refactor `katalog/+page.svelte`:
  - Remove sidebar layout (grid: 220px 1fr → single column)
  - Remove duplicated filter code (sidebar + sheet)
  - Wire FilterBar component with filter state

**Files:**
- `streamfinder/src/lib/components/FilterBar.svelte` — new
- `streamfinder/src/lib/components/FilterDropdown.svelte` — new
- `streamfinder/src/lib/components/ActiveFilters.svelte` — new
- `streamfinder/src/routes/katalog/+page.svelte` — major refactor

**Acceptance criteria:**
- [ ] Horizontal bar renders with 9 category buttons
- [ ] Hover opens empty dropdown shells (no content yet)
- [ ] Mobile shows no bar; FAB + bottom sheet still works
- [ ] No visual regression in title grid layout

---

### Phase 4: Dropdown content — pills, autocomplete, sliders

Implement the 4 dropdown content types.

**Tasks:**
- [ ] Create `src/lib/components/PillGrid.svelte`
  - Props: `items: {name, count, hit}[]`, `selected: string[]`, `onToggle`
  - Flex-wrap grid of pill buttons
  - Active = amber, disabled = opacity 0.35 (existing design tokens)
  - Reused in both FilterBar dropdowns and mobile bottom sheet
- [ ] Create `src/lib/components/AutocompleteDropdown.svelte`
  - Props: `items`, `selected`, `onSelect`, `onRemove`, `placeholder`
  - Text input at top, filtered results below (max 20 shown)
  - Selected values as removable pills above input
  - For Tvůrci: results show "Name (Role, count)" format
  - Debounce input 150ms
- [ ] Create `src/lib/components/RangeSlider.svelte`
  - Props: `min`, `max`, `valueFrom`, `valueTo`, `step`, `onChange`
  - Dual mode (year: from-to) and single mode (rating: min only)
  - Two overlapping `<input type="range">` with custom track styling
  - Value labels above thumbs
  - Swap from/to silently if crossover
  - Keyboard: arrow keys with step increments
- [ ] Wire all dropdown content into FilterDropdown instances in FilterBar
- [ ] Update mobile bottom sheet to use same PillGrid/AutocompleteDropdown/RangeSlider components

**Files:**
- `streamfinder/src/lib/components/PillGrid.svelte` — new
- `streamfinder/src/lib/components/AutocompleteDropdown.svelte` — new
- `streamfinder/src/lib/components/RangeSlider.svelte` — new
- `streamfinder/src/lib/components/FilterBar.svelte` — wire content
- `streamfinder/src/routes/katalog/+page.svelte` — wire mobile sheet

**Acceptance criteria:**
- [ ] All 4 dropdown types work: pill grid, autocomplete, range slider, search
- [ ] Pill dropdowns show hit/disabled state based on current filter intersection
- [ ] Autocomplete filters results reactively as user types
- [ ] Range sliders update filter state on drag
- [ ] Mobile bottom sheet has all filters including new ones (Tvůrci, sliders)

---

### Phase 5: Crew filtering logic + lazy loading

Wire crew filtering into the catalog's derived filter chain.

**Tasks:**
- [ ] Implement `loadCrewIndex()` trigger on first Tvůrci dropdown hover
  - Show spinner in dropdown while loading
  - After load, merge crew data into in-memory title state
- [ ] Add crew filtering to the `filtered` derived computation:
  - If selectedCrew is empty → no filter
  - Otherwise: title passes if any of its `crew_ids` maps to a name in `selectedCrew`
- [ ] Handle URL deep link with `?crew=X`:
  - On page load, if crew params present, trigger immediate crew_index.json load
  - Show "Načítání tvůrců..." placeholder until loaded, then re-filter
- [ ] Add `crew` to URL sync effect (using repeated params)
- [ ] Add crew to ActiveFilters chip display

**Files:**
- `streamfinder/src/routes/katalog/+page.svelte` — filter logic
- `streamfinder/src/lib/data/crew.ts` — lazy loader
- `streamfinder/src/routes/katalog/+page.ts` — URL parsing

**Acceptance criteria:**
- [ ] Selecting "Christopher Nolan" in Tvůrci shows only his films
- [ ] Crew filter combines with other filters (AND logic)
- [ ] URL `?crew=Christopher+Nolan` works on direct navigation
- [ ] First crew interaction loads crew_index.json (visible in network tab)
- [ ] Subsequent interactions use cached data

---

### Phase 6: Polish + testing

Final visual polish, edge case handling, and cross-browser verification.

**Tasks:**
- [ ] Visual polish: hover transitions, dropdown shadows, scrollbar styling
- [ ] Touch device handling: `@media (pointer: coarse)` → click-to-toggle instead of hover
- [ ] Dropdown viewport edge detection: flip alignment if would overflow right edge
- [ ] Empty state: "Žádné výsledky" when all filters combined return 0 titles
- [ ] Performance check: verify filter computation stays < 50ms for 6096 titles
- [ ] Test: hover open/close timing across Chrome, Firefox, Safari
- [ ] Test: mobile bottom sheet with all new filters
- [ ] Test: URL round-trip (set filters → copy URL → paste → same filters active)
- [ ] Push updated JSON data files to GitHub remote

**Acceptance criteria:**
- [ ] No visual regressions on homepage, kalendar, insights, detail pages
- [ ] All filters work on desktop (hover) and mobile (bottom sheet)
- [ ] URL sharing preserves all filter state including crew
- [ ] Page load with crew URL param works without flash of unfiltered content

## Data Size Impact Estimate

| File | Before | After (est.) | Gzipped after |
|------|--------|-------------|---------------|
| titles_index.json | 3.3 MB | ~4.0 MB (+crew_ids) | ~800 KB |
| crew_index.json | N/A | ~800 KB | ~280 KB |
| dimensions.json | 71 KB | ~75 KB (+top 50 crew) | ~15 KB |
| **Total initial load** | **3.4 MB** | **4.1 MB** | **~815 KB** |
| **Crew lazy load** | — | **800 KB** | **~280 KB** |

Initial payload increase: ~20% raw, ~25% gzipped. Crew data loads only on demand.

## Component Architecture

```
katalog/+page.svelte
├── FilterBar.svelte (desktop only, hidden <640px)
│   ├── FilterDropdown.svelte × 6 (hover wrapper)
│   │   ├── PillGrid.svelte (Žáner, Platforma, Krajina, Typ)
│   │   ├── AutocompleteDropdown.svelte (Tagy, Tvůrci)
│   │   └── RangeSlider.svelte (Rok, Hodnocení)
│   └── search input (Název, always visible)
├── ActiveFilters.svelte (chip row below bar)
├── PosterCard grid (existing)
├── TitleModal (existing)
└── Mobile bottom sheet (reuses PillGrid, AutocompleteDropdown, RangeSlider)
```

## Sources & References

### Origin

- **Brainstorm document:** [docs/brainstorms/2026-04-15-catalog-horizontal-filter-bar-brainstorm.md](docs/brainstorms/2026-04-15-catalog-horizontal-filter-bar-brainstorm.md)
  - Key decisions: horizontal layout, hover dropdowns, crew as single autocomplete, range sliders, mobile bottom sheet preserved

### Internal References

- Current catalog page: `streamfinder/src/routes/katalog/+page.svelte` (857 lines, sidebar layout at line 611, filter groups lines 278-405)
- Data loader: `streamfinder/src/routes/katalog/+page.ts` (URL params lines 6-35)
- Types: `streamfinder/src/lib/types.ts` (TitleIndex lines 1-18, no crew)
- Design tokens: `streamfinder/src/app.css` (pill styles lines 126-156, colors lines 4-19)
- Python exporter: `src/csfd_vod/export/streamfinder_exporter.py` (dimensions builder line 284)
- Integration solution (contract testing): `docs/solutions/integration-issues/streamfinder-data-pipeline-frontend-mismatches.md`

---
status: pending
priority: p2
issue_id: "014"
tags: [code-review, svelte, simplification, kalendar]
dependencies: []
---

# Simplification: duplicate fallback in `openModal` + IIFE in `allDates`

## Problem Statement
Two simplification opportunities in `kalendar/+page.svelte`:

**A)** `openModal` has an identical fallback object typed in two separate places — one for a missing cache key, one for a fetch error. 12 lines of duplication.

**B)** `allDates` uses an inline IIFE with a `while` loop and date mutation. Readable on first pass, but a named helper function would be clearer and independently testable.

## Findings

### Finding A — Duplicate fallback object
- **File:** `streamfinder/src/routes/kalendar/+page.svelte` lines ~139–165
- Both the "missing cache key" branch and the `catch` block return the exact same object structure
- If a new `TitleDetail` field is added, it must be updated in two places

### Finding B — IIFE in `allDates`
- **File:** `streamfinder/src/routes/kalendar/+page.svelte` lines 34–43
- A `while` loop with mutable cursor inside an IIFE inside `$derived` is non-obvious
- The logic (generate ISO date range array) is a general utility worth naming

## Proposed Solutions

### Fix A: Extract `emptyDetail` helper

```ts
function emptyDetail(t: TitleIndex): TitleDetail {
    return {
        ...t,
        plot: null,
        backdrop: null,
        trailer_youtube_id: null,
        age_rating: null,
        directors: [],
        actors: [],
        screenwriters: [],
        cinematographers: [],
        composers: [],
        reviews: [],
        vods: []
    };
}
```

Then both branches become `emptyDetail(t)`. Removes ~12 lines.

### Fix B: Extract `dateRange` helper

```ts
function dateRange(from: string, to: string): string[] {
    const dates: string[] = [];
    const cur = new Date(from + 'T12:00:00');
    const end = new Date(to + 'T12:00:00');
    while (cur <= end) {
        dates.push(cur.toISOString().slice(0, 10));
        cur.setDate(cur.getDate() + 1);
    }
    return dates.toReversed(); // newest first, ES2023
}

let allDates = $derived(dateRange(minDate, TODAY));
```

- `toReversed()` instead of `reverse()` — non-mutating, clearer intent (ES2023, available in all modern browsers)
- `$derived` becomes a one-liner

## Recommended Action
Both fixes. Small, isolated, no behavior change.

## Technical Details
- **File:** `streamfinder/src/routes/kalendar/+page.svelte`
- **Lines:** ~34–43 (allDates), ~128–165 (openModal)

## Acceptance Criteria
- [ ] `openModal` on a title with no cache entry returns correct empty detail structure
- [ ] `openModal` on a fetch error returns correct empty detail structure
- [ ] Calendar renders all dates correctly for any `daysBack` value
- [ ] No behavior change observable in the UI

## Work Log
- 2026-04-16: Identified by code-simplicity-reviewer (P2)

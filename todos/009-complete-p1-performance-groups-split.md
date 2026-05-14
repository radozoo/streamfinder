---
status: pending
priority: p1
issue_id: "009"
tags: [code-review, svelte, performance, kalendar]
dependencies: []
---

# Kalendár: split `groups` derived to avoid full O(n) rebuild on filter change

## Problem Statement
The `groups` `$derived.by` block in `kalendar/+page.svelte` does two things at once: it builds a `Map<date, TitleIndex[]>` by scanning all `data.titles` (O(n)), and it applies per-day filters on the result. Both a `daysBack` change AND any filter change (`selectedPlatform`, `selectedType`, `selectedGenre`) invalidate the entire block. When the user changes a filter pill, the expensive O(n) Map rebuild runs unnecessarily — the Map hasn't changed, only the filter selection has.

At 5000 titles this causes 10–30ms per filter click on desktop; on low-end mobile it can reach 20–50ms, approaching the "perceptible lag" threshold.

## Findings
- **File:** `streamfinder/src/routes/kalendar/+page.svelte` lines 66–84
- **Root cause:** Single derived block mixes two concerns: "which titles are in range?" (depends on `daysBack`) and "which titles pass the filters?" (depends on filter state)
- **Impact:** Every filter pill click triggers full O(n) scan of all titles unnecessarily

## Proposed Solutions

### Option A: Two-layer derived (Recommended)

```ts
// Layer 1: rebuilds only when daysBack changes
let titlesInRange = $derived.by(() => {
    const map = new Map<string, TitleIndex[]>();
    for (const t of data.titles) {
        if (!t.vod_date || t.vod_date < minDate || t.vod_date > TODAY) continue;
        const arr = map.get(t.vod_date) ?? [];
        arr.push(t);
        map.set(t.vod_date, arr);
    }
    return map;
});

// Layer 2: rebuilds only when filter selection or allDates change
let groups = $derived.by((): DayGroup[] => {
    return allDates.map((date: string) => {
        let titles = [...(titlesInRange.get(date) ?? [])];
        if (selectedPlatform) titles = titles.filter((t) => t.platforms.includes(selectedPlatform));
        if (selectedType)     titles = titles.filter((t) => t.title_type === selectedType);
        if (selectedGenre)    titles = titles.filter((t) => t.genres.includes(selectedGenre));
        titles.sort((a, b) => (b.rating ?? 0) - (a.rating ?? 0));
        const { label, dayName } = formatDateLabel(date);
        return { date, label, dayName, titles, isToday: date === TODAY };
    });
});
```

- **Pros:** Filter changes skip O(n) scan entirely; `daysBack` changes still correctly rebuild titlesInRange; clean separation of concerns
- **Cons:** Slight increase in code, one more derived variable
- **Effort:** Small
- **Risk:** Low

### Option B: Accept current approach
At current dataset size (<1000 titles) the performance is imperceptible. Defer until data grows.

- **Pros:** No change needed now
- **Cons:** Technical debt accumulates; harder to refactor later when dataset is larger
- **Effort:** None
- **Risk:** Low (now), Medium (later)

## Recommended Action
Option A. Small change, correct architecture, prevents a known performance cliff.

## Technical Details
- **File:** `streamfinder/src/routes/kalendar/+page.svelte` lines 66–84
- **Also fix in same pass:** `typeOptions` (runs 4 separate `data.titles.some()` calls — see todo 013)

## Acceptance Criteria
- [ ] Clicking a filter pill does NOT trigger `titlesInRange` recomputation (verify with Svelte devtools or console.count)
- [ ] Clicking "Zobraz ďalšie dni" correctly rebuilds `titlesInRange` (new dates appear)
- [ ] Filter results are identical before and after the refactor

## Work Log
- 2026-04-16: Identified by performance-oracle agent

---
title: "Svelte 5 $derived.by over-invalidation — split slow and fast dependencies"
date: 2026-04-16
category: performance-issues
tags: [svelte, sveltekit5, derived, reactivity, memoization, performance, calendar]
components: [src/routes/kalendar/+page.svelte]
symptoms:
  - "Changing any filter pill (platform, type, genre) triggers a full O(n) scan of all titles"
  - "Clicking 'load more days' also re-applies every filter unnecessarily"
  - "typeOptions recomputes on minDate changes even though it only depends on the full title list"
root_causes:
  - "$derived.by combined two concerns: building a Map<date, TitleIndex[]> from all titles AND applying per-day filters"
  - "Any dependency of either concern invalidated the entire combined computation — Svelte invalidates at derived granularity, not at line granularity"
  - "typeOptions used four separate data.titles.some() calls inside a $derived that also tracked minDate"
---

# Svelte 5 `$derived.by` over-invalidation — split slow and fast dependencies

## Problem Statement

A single `$derived.by` block in `kalendar/+page.svelte` produced `DayGroup[]` for the timeline. It did two things in one pass:

1. **Slow path** — scanned all `data.titles` to build a `Map<date, TitleIndex[]>`, filtering by `minDate` (changes only when `daysBack` changes — infrequently)
2. **Fast path** — for each date in `allDates`, looked up titles from the map and applied `selectedPlatform`, `selectedType`, `selectedGenre` filters (change on every user interaction)

Because Svelte 5 tracks reactive dependencies at the `$derived` level, *any* change to *any* dependency of the block re-ran the full computation. Every filter pill click triggered the O(n) title scan even though the map hadn't changed.

Separately, `typeOptions` ran four independent `data.titles.some()` calls inside a `$derived` that tracked `minDate`, causing 4 × O(n) work on every "load more days" click.

## Solution

### Split `groups` into two layers

**Layer 1 — rebuilds only when `daysBack` changes:**

```ts
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
```

This derived reads `minDate` (from `daysBack`) and `data.titles`. It only re-runs when those change — i.e. when the user clicks "load more days", not on every filter interaction.

**Layer 2 — rebuilds only when filters or `allDates` change:**

```ts
let groups = $derived.by((): DayGroup[] => {
    return allDates.map((date) => {
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

This derived reads `titlesInRange`, `allDates`, and the three filter states. A filter change only re-runs Layer 2 (cheap: map lookups + filter over per-day arrays). A `daysBack` change re-runs Layer 1 then Layer 2 (unavoidable — the map genuinely changes).

### Rewrite `typeOptions` as a single-pass scan with early exit

**Before** (4 × O(n) — each `.some()` is an independent scan):

```ts
let typeOptions = $derived(
    ['film', 'seriál', 'tv film', 'pořad'].filter((type) =>
        data.titles.some((t) => t.title_type === type && t.vod_date != null && t.vod_date >= minDate)
    )
);
```

**After** (1 × O(n) with early exit once all 4 types are found):

```ts
let typeOptions = $derived.by(() => {
    const seen = new Set<string>();
    const candidates = new Set(['film', 'seriál', 'tv film', 'pořad']);
    for (const t of data.titles) {
        if (t.title_type && candidates.has(t.title_type) && t.vod_date != null && t.vod_date >= minDate) {
            seen.add(t.title_type);
            if (seen.size === candidates.size) break;  // all types found — stop scanning
        }
    }
    return ['film', 'seriál', 'tv film', 'pořad'].filter((t) => seen.has(t));  // preserve order
});
```

Note: `typeOptions` still reads `minDate`, so it still re-runs when `daysBack` changes. The win is in the per-run cost: one pass instead of four.

## Prevention & Best Practices

### Recognize the pattern before it becomes a problem

A single `$derived.by` that mixes concerns of **different change frequency** is a performance trap waiting to fire at scale.

**Warning signals:**
- The block reads both "stable inputs" (dataset loaded once, changes rarely) and "volatile inputs" (UI state that changes per click)
- The block is longer than ~5 lines and contains a `for` loop
- Comments like `// TODO: this might be slow on large datasets` appear inside a derived

### The rule

> **Derived granularity should match change frequency.** If two inputs change at different rates, separate them into two derived values and compose: `slowExpensive` → `fastCheap`.

```
    daysBack ──→ titlesInRange (O(n), rebuilds rarely)
                        ↓
    filters  ──→ groups          (O(days), rebuilds on every filter change)
```

### Checklist for new list/timeline components

- [ ] For each `$derived.by`, list every reactive value it reads. Group by change frequency.
- [ ] If the block reads both dataset-level state (loads once) and interaction-level state (per click), split into two derived values
- [ ] The inner slow derived reads *only* stable inputs; the outer fast derived reads the result of the slow one plus the volatile inputs
- [ ] For "does X exist in the dataset?" checks, prefer a single-pass scan with early exit over multiple `.some()` / `.filter()` calls

### Complexity reference

| Scenario | Old cost | New cost |
|---|---|---|
| Filter pill click (platform/type/genre) | O(n) title scan + O(days) filter | O(days) filter only |
| "Load more days" click | O(n) scan + O(days) filter | O(n) scan + O(days) filter (unavoidable) |
| `typeOptions` on daysBack change | 4 × O(n) early-exit | 1 × O(n) with early exit |

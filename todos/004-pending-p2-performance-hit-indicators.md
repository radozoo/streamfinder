---
status: pending
priority: p2
issue_id: "004"
tags: [code-review, performance, svelte]
---

# Performance: O(n*m) hit-indicator derivations + crew array allocations

## Problem Statement
Two performance issues that are fine at 2514 titles but will cause frame drops before the dataset doubles.

## Findings

### 1. Hit-indicator derivations O(n*m) — `+page.svelte` lines 135–158
Each of `availableGenres`, `availablePlatforms`, `availableCountries`, `availableTags` calls `filtered.some((t) => t.X.includes(g.name))` — that's O(filtered * dim_count * values_per_title) per filter change. ~60k string comparisons per interaction for genres alone.

**Fix:** Build Sets in one O(n) pass:
```ts
let hitGenres = $derived.by(() => {
    const s = new Set<string>();
    for (const t of filtered) for (const g of t.genres) s.add(g);
    return s;
});
let availableGenres = $derived(
    data.dimensions.genres.map((g) => ({ ...g, hit: hitGenres.has(g.name) }))
);
// Repeat for platforms, countries, tags
```

### 2. Crew filter allocates fresh array per title — `+page.svelte` line 95
`(t.crew_ids ?? []).map(...).filter(Boolean)` allocates ~2514 arrays per filter evaluation.

**Fix:** Precompute `selectedCrewIds` as a `Set<number>`:
```ts
let selectedCrewIds = $derived.by(() => {
    if (!selectedCrew.length || !crewIdToName) return null;
    const ids = new Set<number>();
    for (const [id, name] of crewIdToName) {
        if (selectedCrew.includes(name)) ids.add(id);
    }
    return ids;
});
// In filter: if (selectedCrewIds && !t.crew_ids?.some(id => selectedCrewIds!.has(id))) return false;
```

### 3. Crew autocomplete O(26k) on each keystroke — pre-lowercase names at load time
In `crew.ts`, store `nameLower` alongside each entry. Convert `selected` to `Set` in the autocomplete `$derived`.

## Acceptance Criteria
- [ ] No `filtered.some()` inside dimension map derivations
- [ ] Crew filter uses `Set<number>` not intermediate string arrays
- [ ] Crew autocomplete pre-lowercases names at load time

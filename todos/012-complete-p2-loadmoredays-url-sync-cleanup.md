---
status: pending
priority: p2
issue_id: "012"
tags: [code-review, svelte, sveltekit, kalendar, simplification]
dependencies: []
---

# Kalendár: `loadMoreDays` zbytočne parsuje `window.location.search`

## Problem Statement
`loadMoreDays()` reads `window.location.search`, parses it as `URLSearchParams`, sets `?days=`, and stringifies it. This is unnecessary: `?days` is the only managed URL param on the calendar route. Parsing the full URL to preserve "unknown params that don't exist" is YAGNI and creates a misleading dependency on `window.location` instead of the known reactive state.

Additionally, once todo 010 (filter URL serialization) is implemented, `loadMoreDays` should write ALL filter params consistently — using a `$effect` (like the catalog) rather than an ad-hoc imperative write in this function.

## Findings
- **File:** `streamfinder/src/routes/kalendar/+page.svelte` lines 45–50
- **Current:**
  ```ts
  function loadMoreDays() {
      daysBack = Math.min(daysBack + 14, MAX_DAYS);
      const params = new URLSearchParams(window.location.search);
      params.set('days', String(daysBack));
      history.replaceState(null, '', '?' + params.toString());
  }
  ```
- **Problem 1:** `URLSearchParams(window.location.search)` reads stale URL state; `daysBack` is always current
- **Problem 2:** Inconsistent with `katalog/+page.svelte` URL sync pattern (which uses `$effect`)
- **Problem 3:** Once filter URL params are added (todo 010), this function would also need to write `?platform=`, `?type=`, `?genre=` — the `$effect` pattern handles this automatically

## Proposed Solutions

### Option A: Simplify to direct write now (Recommended short-term)

```ts
function loadMoreDays() {
    daysBack = Math.min(daysBack + 14, MAX_DAYS);
    history.replaceState(null, '', '?days=' + daysBack);
}
```

Removes the `URLSearchParams` allocation. 2 lines fewer.

- **Effort:** Tiny
- **Risk:** None
- **Caveat:** Must be updated again once filter URL params added (todo 010)

### Option B: Migrate to `$effect` for all URL sync (Best long-term, pairs with todo 010)

Remove the `history.replaceState` call from `loadMoreDays` entirely. Add a single `$effect` that handles all URL state:

```ts
$effect(() => {
    const params = new URLSearchParams();
    if (daysBack !== 28)  params.set('days', String(daysBack));
    // (filter params added when todo 010 is implemented)
    const qs = params.toString();
    history.replaceState(null, '', qs ? '?' + qs : location.pathname);
});

function loadMoreDays() {
    daysBack = Math.min(daysBack + 14, MAX_DAYS);
    // URL sync handled by $effect
}
```

This makes `loadMoreDays` a pure state mutation. URL is always in sync with state, not the other way around.

- **Effort:** Small
- **Risk:** Low
- **Pros:** Consistent with catalog; single source of URL truth; future filter params added to one place

## Recommended Action
Option B — implement alongside todo 010 (filter URL serialization). They belong in the same commit.

## Technical Details
- **File:** `streamfinder/src/routes/kalendar/+page.svelte` lines 45–50
- **Related:** todo 010 (filter URL serialization), `katalog/+page.svelte` lines 117-132 (reference pattern)

## Acceptance Criteria
- [ ] Clicking "Zobraz ďalšie dni" still updates URL correctly
- [ ] `loadMoreDays()` does not reference `window.location.search`
- [ ] URL sync logic is in one place (`$effect`), not in both `loadMoreDays` and `$effect`

## Work Log
- 2026-04-16: Identified by code-simplicity-reviewer (P1) and typescript-reviewer (P2-C)

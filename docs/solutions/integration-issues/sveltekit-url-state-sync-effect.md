---
title: "SvelteKit URL state sync via $effect + history.replaceState"
date: 2026-04-16
category: integration-issues
tags: [svelte, sveltekit5, url-params, history-replacestate, effect, untrack, state-sync]
components: [src/routes/kalendar/+page.svelte, src/routes/kalendar/+page.ts, src/routes/katalog/+page.svelte]
symptoms:
  - "Filter state resets to defaults on page reload — selections not preserved in URL"
  - "Sharing a filtered URL opens the page with no filters applied"
  - "URL sync logic duplicated across multiple event handlers (loadMoreDays, onToggleFilter, ...)"
  - "history.replaceState called inside event handlers alongside window.location.search parsing"
root_causes:
  - "Filter state stored only as $state — not read from URL on load and not written back on change"
  - "URL writes scattered in event handlers instead of a single reactive effect"
  - "window.location.search parsing in event handlers reads stale URL state; local $state is always current"
---

# SvelteKit URL state sync via `$effect` + `history.replaceState`

## Problem Statement

The calendar page (`/kalendar`) had filter state (`selectedPlatform`, `selectedType`, `selectedGenre`, `daysBack`) stored as local `$state` variables. On reload, those values were always reset to defaults. Sharing a filtered URL opened the page without the filters applied.

Additionally, `loadMoreDays()` contained its own ad-hoc URL write:

```ts
// ❌ Anti-pattern: imperative URL writes inside event handlers
function loadMoreDays() {
    daysBack = Math.min(daysBack + 14, MAX_DAYS);
    const params = new URLSearchParams(window.location.search);  // reads stale URL
    params.set('days', String(daysBack));
    history.replaceState(null, '', '?' + params.toString());
}
```

Problems with this approach:
1. `window.location.search` may be stale — `daysBack` local state is always current
2. Adding a new filter param requires modifying N event handlers
3. URL construction logic is not in one place — diverges over time

## Solution

### Principle: state is source of truth, URL is a derived side-effect

```
$state (selectedPlatform, selectedType, selectedGenre, daysBack)
    ↓
$effect (reads all state, writes URL once)
    ↓
history.replaceState(...)
```

Event handlers only mutate local state. The `$effect` observes all state and produces the URL. Adding a new filter param requires changing only two places: the state declaration and the `$effect`.

### Step 1: Read all filter params in `+page.ts`

```ts
export const load: PageLoad = async ({ parent, url }) => {
    const { titles, dimensions } = await parent();
    // Guard against Number('') === 0 edge case
    const raw = url.searchParams.get('days');
    const initialDays = raw ? Math.min(Math.max(Number(raw), 28), 365) : 28;
    return {
        titles,
        dimensions,
        initialDays,
        initialPlatform: url.searchParams.get('platform') ?? '',
        initialType:     url.searchParams.get('type')     ?? '',
        initialGenre:    url.searchParams.get('genre')    ?? '',
    };
};
```

**Why parse in `load()` instead of in the component?** SvelteKit's `load` function runs server-side (or in prerender) and has access to the canonical URL. Parsing in `load` means the initial render is correct before any JS executes — important for SSR and prerender correctness.

**`Number('')` trap:** `Number('')` returns `0`, not `NaN`. If `?days=` (empty value) appears in the URL, `Number(url.searchParams.get('days') ?? 28)` silently uses `0`. The guard `raw ? ... : 28` avoids this: an empty or absent param always uses the default.

### Step 2: Initialize `$state` from `data` using `untrack`

```ts
// untrack: seed once from URL param, then manage locally
// Without untrack, SvelteKit navigation updating `data` would re-initialize daysBack
let daysBack        = $state<number>(untrack(() => data.initialDays));
let selectedPlatform = $state(untrack(() => data.initialPlatform));
let selectedType     = $state(untrack(() => data.initialType));
let selectedGenre    = $state(untrack(() => data.initialGenre));
```

**Why `untrack()`?** In SvelteKit with client-side navigation, `data` is reactive — it updates when SvelteKit navigates to the same route with different params. Without `untrack`, the `$state` initializer would be re-evaluated on navigation (resetting user-edited state). `untrack` breaks the reactive dependency so the state is seeded once at mount from the server-provided value and then owned locally by the component.

### Step 3: Single `$effect` owns all URL writes

```ts
$effect(() => {
    const params = new URLSearchParams();
    if (daysBack !== 28)    params.set('days',     String(daysBack));
    if (selectedPlatform)   params.set('platform', selectedPlatform);
    if (selectedType)       params.set('type',     selectedType);
    if (selectedGenre)      params.set('genre',    selectedGenre);
    const qs = params.toString();
    history.replaceState(null, '', qs ? '?' + qs : location.pathname);
});
```

**Why omit default values from URL?** `?days=28&platform=&type=&genre=` is ugly and leaks internals. Only non-default values appear in the URL — clean, shareable links.

**`history.replaceState` vs `goto()`:** `goto()` triggers SvelteKit navigation, re-running the `load` function and causing a full component re-mount. `history.replaceState` updates the URL silently without navigation — correct for filter changes that should not reload data.

### Step 4: Event handlers become pure state mutations

```ts
// ✅ Clean: event handlers only mutate state
function loadMoreDays() {
    daysBack = Math.min(daysBack + 14, MAX_DAYS);
    // URL sync handled automatically by the $effect above
}
```

## Prevention & Best Practices

### The rule

> **State is the source of truth. The URL is a derived side-effect of state. Write state; let one `$effect` translate the full state snapshot into a URL update. Never write the URL directly from an event handler.**

### Recognize the anti-pattern

| Signal | Problem |
|---|---|
| `history.replaceState` or `goto()` in an event handler | URL writes scattered, diverge over time |
| `new URLSearchParams(window.location.search)` in a handler | Reading stale URL state; use local `$state` |
| URL sync logic duplicated in 2+ handlers | Adding a new param requires N edits |
| Filter state initialised as `$state('')` with no URL read | State does not survive reload |

### Checklist for new filtered pages

- [ ] All filterable state read from URL params in `+page.ts` `load()` as `initialXxx`
- [ ] Component state initialised from `data.initialXxx` via `untrack()`
- [ ] Exactly **one** `$effect` owns all `history.replaceState` calls
- [ ] Default values omitted from URL (clean links: `?genre=Drama` not `?days=28&platform=&genre=Drama`)
- [ ] Event handlers only mutate `$state` — never touch `history` directly
- [ ] `+page.ts` guards against `Number('')` edge case when parsing numeric params

### When to use `goto()` instead of `history.replaceState`

Use `goto()` (SvelteKit navigation) when the URL change should trigger a server `load` call — e.g. navigating to a different page, or when `load` performs data fetching that depends on the URL param.

Use `history.replaceState` when all data is already loaded client-side and the URL update is purely for shareability/back-button behavior — e.g. filter state over a locally-held dataset.

## Related

- [FilterDropdown overflow clipping + singleton state](../ui-bugs/svelte-dropdown-overflow-clip-and-singleton-state.md) — same `untrack()` pattern for initializing dropdown open state from props

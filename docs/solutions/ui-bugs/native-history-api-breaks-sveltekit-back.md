---
id: "2026-08-01-history-api-breaks-sveltekit-back"
date: "2026-08-01"
project: "csfd/streamfinder"
scope:
  - "streamfinder/src/routes/katalog/+page.svelte"
  - "streamfinder/src/routes/kalendar/+page.svelte"
guard: "streamfinder/e2e/url-state.mjs (npm run test:e2e); streamfinder/src/lib/history-api.test.ts"
tags:
  - ui-bugs
  - sveltekit
  - routing
  - history-api
  - silent-failure
---

# Three ways to write the URL, and only one of them survives the Back button

Katalóg and Kalendár keep their filter state in the URL, written from an `$effect`.
Two of the three plausible APIs for that are wrong, and both were shipped in turn —
the second while fixing the first.

## Attempt 1: the browser's own API

```js
history.replaceState(null, '', '?' + params);
```

**Symptom:** open a title, press Back — nothing happens. Press Back again and you
land two pages away, having skipped the list you came from.

**Cause:** the first argument is the history *state object*, and SvelteKit keeps its
router index there. `null` wipes it. The router's popstate handler opens with:

```js
if (event.state?.[HISTORY_INDEX]) { ... }   // the real navigation
else { if (!hash_navigating) update_url(url); }   // URL only, no navigation
```

With the state gone every popstate took the `else` branch: the address bar moved
back, the rendered page did not.

## Attempt 2: SvelteKit's `replaceState`

```js
import { replaceState } from '$app/navigation';
replaceState('?' + params, {});
```

**Symptom:** Back now navigates, but the filters are gone — you return to an
unfiltered Katalóg.

**Cause:** `replaceState` is a *shallow routing* API. It attaches state to the
current page, and it records the entry's URL as the page's own:

```js
const opts = {
    [HISTORY_INDEX]: current_history_index,
    [NAVIGATION_INDEX]: current_navigation_index,
    [PAGE_URL_KEY]: page.url.href      // ← the CURRENT page, not the url argument
};
```

So the address bar showed `?q=batman` while the history entry recorded `/katalog`.
Back restored the entry, not the address bar. Visible directly in `history.state`:

```
href                    /katalog?q=batman
sveltekit:pageurl       http://localhost:5199/katalog
```

It also throws — `Cannot call replaceState(...) before router is initialized` — when
called from an `$effect` during mount. The throw broke the effect outright, so the
URL was never written at all, which is a second reason the filters had nothing to
come back to.

## What works: `goto`

```js
goto(params ? '?' + params : location.pathname, {
    replaceState: true,   // one entry per page, not one per keystroke
    keepFocus: true,      // do not steal the caret out of the search field
    noScroll: true        // do not jump the grid
});
```

`goto` performs a real client-side navigation, so the filtered URL becomes the thing
the history entry holds and Back returns to. It needs the same router-ready guard:

```js
let routerReady = $state(false);
afterNavigate(() => (routerReady = true));

$effect(() => {
    const params = buildParams();   // read the dependencies FIRST
    if (!routerReady) return;       // …so this still re-runs once ready
    goto(...);
});
```

## Why none of it was caught

Every automated signal was green for both attempts. They type-check, they build,
`svelte-check` is silent, and in attempt 2 the URL in the address bar was correct —
a screenshot or a casual click-through looks perfect. The defect lived in
`history.state`, and surfaced only under a real Back navigation.

The source-level guard written after attempt 1 (`history-api.test.ts`, which fails on
any native `history.replaceState`/`pushState`) would not have caught attempt 2 at
all: that code used the officially-recommended import. Banning it outright would be
wrong too — it is the right API for shallow routing. Some bugs cannot be found by
reading the source, only by driving the thing.

## Prevention

- [x] `e2e/url-state.mjs` (`npm run test:e2e`) starts a dev server, filters both
      pages, opens a title, presses Back, and asserts on the *rendered grid* rather
      than the URL. Verified against both bugs: attempt 1 fails as a timeout (Back
      never navigates), attempt 2 fails three checks (URL, input, grid) while still
      passing "Back leaves the detail page" — a distinct signature per cause.
- [x] The e2e reports a timeout as a named failure instead of crashing, so a broken
      Back button does not take the summary and the server shutdown with it.
- [x] `history-api.test.ts` still bans the native API at source level — cheap, runs
      with the unit tests, and covers the one case that IS visible in the source.
- [ ] Any future "the URL is right but the page is wrong": read `history.state`
      before suspecting the router.

---
id: "2026-08-01-native-history-api-breaks-sveltekit-back"
date: "2026-08-01"
project: "csfd/streamfinder"
scope:
  - "streamfinder/src/routes/katalog/+page.svelte"
  - "streamfinder/src/routes/kalendar/+page.svelte"
guard: "streamfinder/src/lib/history-api.test.ts"
tags:
  - ui-bugs
  - sveltekit
  - routing
  - history-api
  - silent-failure
---

# The browser's own history API silently disabled the Back button

## Symptom

Reported from the Katalóg and the Kalendár: open a title, press Back — nothing
happens. Press Back again and you land on the home page, having skipped the list
you came from.

## Root Cause

Both pages synchronised their filter state into the URL from an `$effect`:

```js
history.replaceState(null, '', str ? '?' + str : location.pathname);
```

That is the browser's API, and its first argument is the history *state object*.
Passing `null` sets `history.state = null` — and SvelteKit keeps its router index in
exactly that object. Its popstate handler opens with:

```js
addEventListener('popstate', async (event) => {
    if (event.state?.[HISTORY_INDEX]) {
        ...      // the real client-side navigation
    } else {
        if (!hash_navigating) {
            const url = new URL(location.href);
            update_url(url);     // updates the URL store — and nothing else
        }
    }
});
```

With the state wiped, every popstate took the `else` branch: the address bar moved
back to `/katalog`, the rendered page did not. The second Back then went one entry
further, to wherever the user had been before — which is why it looked like Back
"skipped" a page rather than being broken.

## Fix

Use SvelteKit's own `replaceState`, which writes the URL while preserving the
router's state:

```js
import { replaceState } from '$app/navigation';
...
replaceState(str ? '?' + str : location.pathname, {});
```

## Why it went unnoticed

Nothing that runs in CI presses the Back button. It type-checks, it builds, no
warning appears, and the URL genuinely changes — so every automated signal and a
casual click-through all look correct. The bug only exists in the gap between the
address bar and the rendered page, and only under a real back navigation.

It also predates the release that exposed it. While Katalóg and Kalendár opened
titles in a modal there was no navigation to come back from, so the broken handler
had nothing to break. Unifying on detail pages made a long-standing latent bug
reachable.

## Prevention

- [x] `history-api.test.ts` sweeps the source (via `import.meta.glob` + `?raw`, so it
      runs in the browser runner alongside the component tests) and fails on any
      `history.replaceState`/`pushState` call. Verified by reintroducing the call.
- [x] The sweep asserts it matched a non-trivial number of files first — a glob that
      silently matches nothing would make the check vacuously pass.
- [ ] Any future "the URL is right but the page is wrong" report: suspect
      `history.state` before suspecting the router.

Verified in a real browser, both directions: with the fix, Back returns to
`/katalog` with 48 cards rendered and no detail heading; with the old line restored,
the same run reports the URL at `/katalog` but 0 cards and the detail heading still
on screen.

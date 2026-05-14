---
status: pending
priority: p3
issue_id: "015"
tags: [code-review, svelte, python, simplification, quality]
dependencies: []
---

# P3 housekeeping: minor code quality items across multiple files

## Problem Statement
Several small code quality issues found during review. None are bugs. Batch them into a single cleanup commit.

## Findings

### 1. `<script module>` missing `lang="ts"` — FilterDropdown.svelte line 1
The instance `<script lang="ts">` is explicit but `<script module>` relies on implicit TypeScript inheritance from Svelte config. Being explicit is safer:
```svelte
<script module lang="ts">
```

### 2. `detailCache` plain `let` in kalendar — inconsistent with katalog
`katalog/+page.svelte` correctly uses `$state` for `detailCache`. `kalendar/+page.svelte` still uses a plain `let`. Works today (cache is read imperatively in `openModal`), but inconsistent and fragile if template ever needs to react to it.
```ts
// From:
let detailCache: Record<string, TitleDetail> | null = null;
// To:
let detailCache = $state<Record<string, TitleDetail> | null>(null);
```

### 3. `_yt_match` naming in Python — non-idiomatic leading underscore
`_yt_match` in `streamfinder_exporter.py` line 322. Leading underscores on local variables suggest class-level privacy in Python. Rename to `yt_match`.

### 4. `untrack()` missing comment — kalendar/+page.svelte line 14
`untrack(() => data.initialDays)` without a comment looks like a workaround. Explain why:
```ts
// untrack: seed once from URL param, then manage locally (prevents re-init on SvelteKit navigation)
let daysBack = $state<number>(untrack(() => data.initialDays));
```

### 5. `clampToRange` is only called by `scrollToDate` — inline it
The 4-line helper adds indirection for a single call site:
```ts
function scrollToDate(date: string) {
    const target = date < minDate ? minDate : date > TODAY ? TODAY : date;
    document.getElementById('day-' + target)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
}
```

### 6. `detailCache ??=` shorthand — kalendar/+page.svelte
Replace 3-line if-block with nullish assignment operator:
```ts
// From:
if (!detailCache) {
    const res = await fetch(`${base}/data/titles_detail.json`);
    detailCache = await res.json();
}
// To:
detailCache ??= await (await fetch(`${base}/data/titles_detail.json`)).json();
```

## Recommended Action
Batch all items into one commit: `refactor(streamfinder): code quality housekeeping`.

## Technical Details
- `streamfinder/src/lib/components/FilterDropdown.svelte` line 1 (item 1)
- `streamfinder/src/routes/kalendar/+page.svelte` lines 14, 100-104, 128, 134 (items 2, 4, 5, 6)
- `src/csfd_vod/export/streamfinder_exporter.py` line 322 (item 3)

## Acceptance Criteria
- [ ] No behavior change in any affected file
- [ ] `svelte-check` still reports 0 errors after changes
- [ ] Python exports still produce identical JSON output

## Work Log
- 2026-04-16: Identified by typescript-reviewer (P3-A, P3-B), python-reviewer (P3), code-simplicity-reviewer (P3)

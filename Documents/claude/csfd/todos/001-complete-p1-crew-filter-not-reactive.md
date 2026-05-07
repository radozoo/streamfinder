---
status: complete
priority: p1
issue_id: "001"
tags: [code-review, svelte, bug]
---

# crewIdToName is not $state — crew filter silently broken

## Problem Statement
`crewIdToName` and `detailCache` are declared as plain JS variables, not `$state`. Svelte 5's reactivity system has no subscription on them, so when `ensureCrewLoaded()` sets `crewIdToName = new Map(...)`, the `filtered` derived does not re-run. Any user who selects a crew filter before hovering the crew dropdown gets permanently empty results (until some other reactive dep forces a re-run).

## Findings
- **File:** `streamfinder/src/routes/katalog/+page.svelte` lines 50, 59
- `let crewIdToName: Map<number, string> | null = null;` — not reactive
- `let detailCache: Record<string, TitleDetail> | null = null;` — not reactive
- The `filtered` `$derived.by` on line 94 reads `crewIdToName` — this read is not tracked

## Fix
```ts
let crewIdToName = $state<Map<number, string> | null>(null);
let detailCache = $state<Record<string, TitleDetail> | null>(null);
```

Also fix the `filter(Boolean)` type narrowing issue on line 95:
```ts
// Wrong — stays (string | undefined)[]
.filter(Boolean)
// Correct
.filter((n): n is string => n !== undefined)
```

## Acceptance Criteria
- [ ] Select a crew member before hovering crew dropdown → results filter correctly
- [ ] `crewIdToName` and `detailCache` declared with `$state`

---
status: pending
priority: p2
issue_id: "013"
tags: [code-review, svelte, performance, kalendar]
dependencies: ["009"]
---

# Performance: `typeOptions` runs 4x scans + `updatePanelPosition` on every hover

## Problem Statement
Two separate performance issues in the same area:

**A) `typeOptions` runs 4 separate `data.titles.some()` scans per `minDate` change**
Each "load more days" click triggers 4 independent early-exit scans of all titles. In the worst case (sparse data) this is 4 × O(n) iterations. At 5000 titles: ~20 000 comparisons per button click.

**B) `updatePanelPosition()` forces layout on every `mouseenter`**
`getBoundingClientRect()` forces a synchronous browser layout flush. Called 8× (one per FilterDropdown instance) on every `mouseenter` event as the user moves the mouse across the filter bar, even when the panel is already open.

## Findings

### Finding A
- **File:** `streamfinder/src/routes/kalendar/+page.svelte` lines 93–97
- **Current:** 4 separate `.filter((type) => data.titles.some(...))` calls
- Each call can scan up to all titles before early-exiting

### Finding B
- **File:** `streamfinder/src/lib/components/FilterDropdown.svelte` lines 51–55
- **Current:** `handleEnter()` calls `updatePanelPosition()` unconditionally
- Position only changes if the element moves — no need to re-measure when panel is already open

## Proposed Solutions

### Fix A: Single-pass typeOptions with early exit

```ts
let typeOptions = $derived.by(() => {
    const seen = new Set<string>();
    const candidates = new Set(['film', 'seriál', 'tv film', 'pořad']);
    for (const t of data.titles) {
        if (t.title_type && candidates.has(t.title_type) && t.vod_date != null && t.vod_date >= minDate) {
            seen.add(t.title_type);
            if (seen.size === candidates.size) break;
        }
    }
    return ['film', 'seriál', 'tv film', 'pořad'].filter(t => seen.has(t));
});
```

- **Effort:** Small
- **Risk:** None — result is identical, just computed in one pass

### Fix B: Guard `updatePanelPosition` when panel is already open

```ts
function handleEnter() {
    cancelClose();
    if (openId !== myId) {  // only re-measure when actually opening
        updatePanelPosition();
    }
    openId = myId;
}
```

- **Effort:** Tiny (one `if` guard)
- **Risk:** None

## Recommended Action
Both fixes are small and independent — implement together.

**Note:** Fix A pairs well with todo 009 (split `groups` into `titlesInRange` + `groups`). Consider combining all performance fixes into one commit.

## Technical Details
- **Files:**
  - `streamfinder/src/routes/kalendar/+page.svelte` lines 93–97 (typeOptions)
  - `streamfinder/src/lib/components/FilterDropdown.svelte` lines 51–55 (handleEnter)

## Acceptance Criteria
- [ ] `typeOptions` uses a single iteration (verify with console.count if needed)
- [ ] Moving mouse across already-open dropdown does not call `getBoundingClientRect()`
- [ ] Filter bar dropdown still opens and positions correctly

## Work Log
- 2026-04-16: Identified by performance-oracle agent (P2)

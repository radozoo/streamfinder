---
status: pending
priority: p1
issue_id: "008"
tags: [code-review, svelte, ui-bugs, position-fixed]
dependencies: []
---

# FilterDropdown: position:fixed panel drifts on scroll/resize

## Problem Statement
`updatePanelPosition()` is called once on open (hover or click) and never again. Because the panel uses `position: fixed` with coordinates from `getBoundingClientRect()`, scrolling the page or resizing the window while the panel is open leaves it floating at the original pixel position, visually detached from the trigger button.

This is explicitly listed in the dropdown/popover checklist in `docs/solutions/ui-bugs/svelte-dropdown-overflow-clip-and-singleton-state.md` (line 219): "Panel closes on page scroll (add `scroll` listener when using `position: fixed`)".

## Findings
- **File:** `streamfinder/src/lib/components/FilterDropdown.svelte` lines 29–34, 51–55
- `updatePanelPosition()` is called in `handleEnter()` (line 53) and `handleClick()` (line 62) but never on scroll or resize
- On desktop the filter bar is near the top of the page — scroll impact is real when the user opens a panel and then scrolls
- `position: fixed` requires the component itself to maintain position sync with scroll events

## Proposed Solutions

### Option A: `$effect` with scroll + resize listeners (Recommended)
Add a `$effect` that wires/unwires window listeners while `open` is true:

```svelte
$effect(() => {
    if (!open) return;
    const update = () => updatePanelPosition();
    window.addEventListener('scroll', update, { passive: true, capture: true });
    window.addEventListener('resize', update, { passive: true });
    return () => {
        window.removeEventListener('scroll', update, { capture: true });
        window.removeEventListener('resize', update);
    };
});
```

- **Pros:** Correct Svelte 5 pattern; auto-cleans up when panel closes; `capture: true` catches scroll on inner scrollable containers too
- **Cons:** Small overhead — adds/removes listeners on every open/close cycle (negligible)
- **Effort:** Small
- **Risk:** Low

### Option B: Close panel on scroll instead of repositioning
On scroll, call `openId = null` to dismiss the panel rather than repositioning it. Simpler and arguably better UX (standard browser dropdown behavior).

```ts
$effect(() => {
    if (!open) return;
    const close = () => { if (openId === myId) openId = null; };
    window.addEventListener('scroll', close, { passive: true, capture: true });
    return () => window.removeEventListener('scroll', close, { capture: true });
});
```

- **Pros:** Even simpler; consistent with native `<select>` behavior
- **Cons:** Might be annoying if user accidentally triggers scroll while interacting with panel
- **Effort:** Tiny
- **Risk:** Low

## Recommended Action
Option A — repositioning is better UX for the rating/year range sliders which require drag interaction. Closing on scroll would make those unusable.

## Technical Details
- **File:** `streamfinder/src/lib/components/FilterDropdown.svelte`
- **Related:** `docs/solutions/ui-bugs/svelte-dropdown-overflow-clip-and-singleton-state.md` checklist item line 219

## Acceptance Criteria
- [ ] Open a filter dropdown
- [ ] Scroll the page — panel follows trigger button
- [ ] Resize the window — panel repositions correctly
- [ ] Panel still closes correctly on mouse leave / focus out

## Work Log
- 2026-04-16: Identified by TypeScript reviewer (P1-B) and confirmed against solution doc checklist

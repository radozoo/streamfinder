---
title: "FilterDropdown: panels clipped by overflow container + simultaneous multi-panel opening"
date: 2026-04-16
category: ui-bugs
tags: [svelte, sveltekit5, dropdown, overflow, css, position-fixed, shared-state, script-module]
components: [FilterDropdown.svelte, FilterBar.svelte]
symptoms:
  - Filter dropdown panels never appeared on hover or click — only CSS color change visible
  - Moving mouse quickly between pills caused multiple panels to be visible simultaneously
root_causes:
  - ".filter-bar has overflow-x: auto which clips position:absolute descendants — panel rendered in DOM but was invisible"
  - "Button had onkeydown but no onclick — mouse clicks never toggled open state"
  - "Each instance had independent open = $state(false) and closeTimer — 150ms delay allowed old panel to stay visible when new one opened"
---

# FilterDropdown: panels clipped by overflow + simultaneous multi-panel opening

## Problem Statement

The horizontal filter bar (`FilterBar.svelte`) wraps a row of `FilterDropdown` instances inside a `display: flex; overflow-x: auto` scroll container. Two bugs made the dropdowns completely non-functional:

1. **Panels never appeared** — hovering or clicking a pill changed its color (CSS `:hover`) but no panel opened.
2. **Multiple panels open at once** — after fixing bug 1, moving the mouse quickly between pills caused both the old and new panels to show simultaneously.

## Findings

### Bug 1: CSS overflow clipping + missing onclick

**`FilterBar.svelte` — scroll container:**
```css
.filter-bar {
    display: flex;
    overflow-x: auto;   /* ← culprit */
}
```

CSS rule: any ancestor with `overflow: auto/scroll/hidden` clips `position: absolute` descendants that overflow its bounds — regardless of `z-index`. The panel was rendering (`open = true`) and existed in the DOM with correct dimensions, but was invisible because it was clipped.

Additionally, the `<button>` trigger had `onkeydown` for keyboard navigation but **no `onclick` handler**, so clicking never changed `open`.

### Bug 2: Race condition between independent instances

Each `FilterDropdown` owned:
```ts
let open = $state(false);
let closeTimer: ReturnType<typeof setTimeout> | null = null;
```

On fast mouse movement (A → B):
1. Mouse leaves A → `scheduleClose()` starts 150ms timer
2. Mouse enters B → `open = true` on B
3. A's timer fires after 150ms → `open = false` on A

During those 150ms, both A and B had `open = true` simultaneously.

## Solution

### Bug 1: position: fixed + DOM sibling + onclick

**Changed panel from `position: absolute` (child) to `position: fixed` (sibling).**

`position: fixed` is relative to the viewport — it escapes every ancestor's overflow context. The panel is rendered outside the `.filter-dropdown` wrapper so it is never subject to `.filter-bar`'s clipping.

Panel position is calculated dynamically via `getBoundingClientRect()` on the trigger button:

```svelte
<script lang="ts">
    let triggerEl = $state<HTMLButtonElement | null>(null);
    let panelTop = $state(0);
    let panelLeft = $state(0);

    function updatePanelPosition() {
        if (!triggerEl) return;
        const rect = triggerEl.getBoundingClientRect();
        panelTop = rect.bottom + 6;
        panelLeft = rect.left;
    }

    function handleEnter() {
        cancelClose();
        updatePanelPosition();
        openId = myId;
    }

    function handleClick() {
        const wasOpen = open;
        if (!wasOpen) updatePanelPosition();
        openId = wasOpen ? null : myId;
        if (wasOpen) pinned = false;
    }
</script>

<!-- Trigger wrapper — stays inside scroll container -->
<div class="filter-dropdown" onmouseenter={handleEnter} onmouseleave={handleLeave} ...>
    <button bind:this={triggerEl} onclick={handleClick} onkeydown={handleKeydown} ...>
        {label}
    </button>
</div>

<!-- Panel rendered as SIBLING — escapes overflow clipping -->
{#if open}
    <div
        class="filter-panel"
        style="top: {panelTop}px; left: {panelLeft}px;"
        onmouseenter={cancelClose}
        onmouseleave={handleLeave}
    >
        {@render children()}
    </div>
{/if}
```

```css
.filter-panel {
    position: fixed;   /* was: absolute */
    z-index: 120;
    /* top/left set via inline style from getBoundingClientRect() */
}
```

Since the panel is now a DOM sibling (not a child of `.filter-dropdown`), it no longer inherits `onmouseenter`/`onmouseleave` from the wrapper via bubbling — those handlers are added directly to the panel element.

### Bug 2: Module-level shared state with Symbol identity

**Lifted open state to `<script module>` — shared across all instances.**

```svelte
<script module>
    // One slot shared across ALL FilterDropdown instances on the page.
    // Setting openId = myId closes every other instance immediately.
    let openId = $state<symbol | null>(null);
</script>

<script lang="ts">
    const myId = Symbol();  // stable unique identity for this instance

    let open = $derived(openId === myId);  // derived, not writable state

    function handleEnter() {
        cancelClose();
        updatePanelPosition();
        openId = myId;  // atomically closes all others
    }

    function scheduleClose() {
        if (pinned) return;
        closeTimer = setTimeout(() => {
            // Guard: only null out if this instance is still the active one.
            // Without this, a stale timer from A would close a newly-opened B.
            if (!pinned && openId === myId) openId = null;
        }, 150);
    }
</script>
```

**Why this eliminates the race:** Setting `openId = myId` is a single synchronous write. All other instances derive `open = $derived(openId === myId)` which instantly becomes `false`. There is no 150ms window where two instances are open.

**The timer guard** (`openId === myId`) ensures that if the user moves from A → B before A's 150ms timer fires, A's timer does nothing — `openId` is already B's symbol.

### Bug 3: position:fixed panel drifts on scroll/resize

`updatePanelPosition()` was called once on open and never again. Because `position: fixed` coordinates are viewport-relative at the moment of `getBoundingClientRect()`, scrolling the page or resizing the window left the panel floating at its original pixel position, visually detached from the trigger.

**Fix:** A `$effect` that wires `scroll` and `resize` listeners while the panel is open, calling `updatePanelPosition()` on each event. The effect cleanup function removes the listeners when `open` becomes `false`.

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

`capture: true` on scroll is required to catch events from inner scrollable containers (e.g. the filter panel itself has `overflow-y: auto`), not only from the window root.

**Also fixed:** `handleEnter` previously called `updatePanelPosition()` unconditionally — forcing a layout flush on every `mouseenter` even when the panel was already open. A guard prevents the redundant measurement:

```ts
function handleEnter() {
    cancelClose();
    if (openId !== myId) updatePanelPosition();  // only measure when actually opening
    openId = myId;
}
```

### Summary of all changes

| Area | Before | After |
|---|---|---|
| Panel positioning | `position: absolute`, child of wrapper | `position: fixed`, sibling outside wrapper |
| Position coordinates | CSS `top: calc(100% + 6px)` | JS `getBoundingClientRect()` inline style |
| Panel mouse events | Bubbled from wrapper | Explicit handlers on panel element |
| Button click | No `onclick` | `onclick={handleClick}` |
| Open state | `$state(false)` per instance | `$state<symbol\|null>(null)` in `<script module>` |
| Close-others | 150ms timer, race-prone | Instantaneous — writing `openId` closes all others |
| Timer safety | None | `if (openId === myId)` guard |
| Scroll/resize drift | Panel frozen at open-time coords | `$effect` re-measures on scroll + resize |
| `getBoundingClientRect` calls | On every `mouseenter` (forced layout) | Only when panel transitions from closed → open |

## Prevention & Best Practices

### position: fixed vs position: absolute for dropdowns

Use `position: fixed` when the trigger lives inside any scrollable or overflow-constrained container. This is the correct default for floating UI (dropdowns, tooltips, popovers).

Use `position: absolute` only when you fully control the ancestor chain and can guarantee no ancestor has `overflow` set to anything other than `visible`.

**Rule of thumb:** if the trigger is inside a scroll container → use `position: fixed`.

### The overflow clipping trap

`overflow: auto/scroll/hidden` on any ancestor clips absolutely-positioned descendants — even if `z-index` is high and the element is not the positioning parent. The element exists in the DOM and has correct dimensions but is invisible.

**How to spot it:**
- DevTools: inspect every ancestor for non-`visible` computed `overflow`
- Add `outline: 2px solid red` to the panel — if the outline is absent but the element is in the DOM, clipping is the cause

**Prevention:** When adding `overflow-x: auto` to a layout container, leave a comment noting it clips absolute descendants and audit whether any dropdown/tooltip lives inside it.

### Svelte 5 `<script module>` for mutually exclusive instances

When multiple component instances are mounted and only one should be active at a time, instance-level `$state` is insufficient — each instance is independent with no sibling awareness.

```svelte
<script module>
    let openId = $state<symbol | null>(null);
</script>

<script>
    const myId = Symbol();
    let isOpen = $derived(openId === myId);

    function open()  { openId = myId; }
    function close() { if (openId === myId) openId = null; }
</script>
```

Use this pattern for: filter bar dropdowns, accordion (one-open), segmented button groups, tooltip anchors.

Do **not** use it when instances are intentionally independent (separate unrelated dropdowns in different UI regions).

### Checklist for new dropdown/popover components

- [ ] Does the trigger live inside a scroll or overflow container? → use `position: fixed`
- [ ] Panel position sourced from `getBoundingClientRect()` on the trigger
- [ ] Every ancestor inspected for `overflow` in DevTools during development
- [ ] Panel repositions on scroll and resize — `$effect` wires `window.scroll` + `window.resize` listeners while open, cleans up in return function
- [ ] Button has `onclick` handler (not only `onkeydown`)
- [ ] If instances are mutually exclusive → shared state in `<script module>` with Symbol identity
- [ ] Timer guards check instance identity before closing shared state
- [ ] `aria-expanded` bound to open state on trigger button
- [ ] Escape key closes panel and returns focus to trigger
- [ ] Tested with two or more instances visible simultaneously

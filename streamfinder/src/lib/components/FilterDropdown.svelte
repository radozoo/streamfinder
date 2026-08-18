<script module lang="ts">
	// One slot shared across ALL FilterDropdown instances on the page.
	// Setting openId = myId atomically closes every other instance.
	let openId = $state<symbol | null>(null);
</script>

<script lang="ts">
	import type { Snippet } from 'svelte';

	let {
		label,
		activeCount = 0,
		children
	}: {
		label: string;
		activeCount?: number;
		children: Snippet;
	} = $props();

	const myId = Symbol();
	let open = $derived(openId === myId);
	let closeTimer: ReturnType<typeof setTimeout> | null = null;
	let triggerEl = $state<HTMLButtonElement | null>(null);
	// The panel is rendered as a DOM sibling (see below), so "is focus still
	// inside this dropdown?" has to ask about both elements, not just the wrapper.
	let panelEl = $state<HTMLElement | null>(null);
	let panelTop = $state(0);
	let panelLeft = $state(0);

	function updatePanelPosition() {
		if (!triggerEl) return;
		const rect = triggerEl.getBoundingClientRect();
		panelTop = rect.bottom + 6;
		panelLeft = rect.left;
	}

	/**
	 * Is focus inside this dropdown AND did the keyboard put it there?
	 *
	 * Decided here, at closing time, rather than carried in a flag set on focusin. Such
	 * a flag cannot tell a keyboard user from a mouse one: clicking a pill focuses it
	 * too, so the panel held itself open on selection and, since focus never follows the
	 * pointer, nothing ever released it — the panel stayed up until you clicked
	 * somewhere else entirely. :focus-visible is the browser's own keyboard-vs-pointer
	 * heuristic, which beats anything guessed from event order here.
	 */
	function focusIsKeyboardInside(): boolean {
		const active = document.activeElement as HTMLElement | null;
		if (!active) return false;
		const inside = active === triggerEl || (panelEl?.contains(active) ?? false);
		if (!inside) return false;
		try {
			return active.matches(':focus-visible');
		} catch {
			// Engine without :focus-visible. Closing is the lesser evil: a panel that
			// overstays is the bug being fixed, and Escape still works.
			return false;
		}
	}

	function scheduleClose() {
		closeTimer = setTimeout(() => {
			// Guard: only close if we are still the active instance.
			// Without this, a stale timer from A could close a newly-opened B.
			if (openId !== myId) return;
			// Never yank the panel away from someone tabbing through it.
			if (focusIsKeyboardInside()) return;
			openId = null;
		}, 150);
	}

	function cancelClose() {
		if (closeTimer) {
			clearTimeout(closeTimer);
			closeTimer = null;
		}
	}

	function handleEnter() {
		cancelClose();
		// Only measure when actually transitioning closed → open
		if (openId !== myId) updatePanelPosition();
		openId = myId;
	}

	function handleLeave() {
		scheduleClose();
	}

	function handleClick() {
		const wasOpen = open;
		if (!wasOpen) updatePanelPosition();
		openId = wasOpen ? null : myId;
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Enter' || e.key === ' ') {
			e.preventDefault();
			handleClick();
		} else if (e.key === 'Escape' && open) {
			openId = null;
		}
	}

	// The panel is a DOM sibling, so a keydown inside it never reaches the wrapper that
	// handles Escape above — pressing it after selecting a pill did nothing at all.
	function handlePanelKeydown(e: KeyboardEvent) {
		if (e.key !== 'Escape') return;
		openId = null;
		// The focused pill is about to leave the document, which would drop the caret to
		// the top of the page; hand focus back to the trigger it came from.
		triggerEl?.focus();
	}

	function handleFocusIn() {
		cancelClose();
	}

	function handleFocusOut(e: FocusEvent) {
		const wrapper = e.currentTarget as HTMLElement;
		// Only unpin if focus leaves the dropdown AND its panel. Checking the wrapper
		// alone closed the panel on the first pill clicked: the panel lives outside the
		// wrapper, so selecting anything in it counted as focus leaving. Every
		// multi-select facet was effectively single-select — you had to reopen the
		// dropdown for each additional value.
		requestAnimationFrame(() => {
			const active = document.activeElement;
			if (!wrapper.contains(active) && !panelEl?.contains(active)) scheduleClose();
		});
	}

	$effect(() => {
		if (!open) return;
		const update = () => updatePanelPosition();
		// capture:true catches scroll from inner overflow containers, not just window root
		window.addEventListener('scroll', update, { passive: true, capture: true });
		window.addEventListener('resize', update, { passive: true });
		return () => {
			window.removeEventListener('scroll', update, { capture: true });
			window.removeEventListener('resize', update);
		};
	});
</script>

<!-- svelte-ignore a11y_no_static_element_interactions -->
<div
	class="filter-dropdown"
	onmouseenter={handleEnter}
	onmouseleave={handleLeave}
	onfocusin={handleFocusIn}
	onfocusout={handleFocusOut}
>
	<button
		bind:this={triggerEl}
		class="filter-trigger"
		class:has-active={activeCount > 0}
		aria-expanded={open}
		aria-haspopup="true"
		onclick={handleClick}
		onkeydown={handleKeydown}
	>
		{label}
		{#if activeCount > 0}
			<span class="filter-badge">{activeCount}</span>
		{/if}
		<svg class="chevron" class:open width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="6 9 12 15 18 9"/></svg>
	</button>
</div>

{#if open}
	<!-- Rendered as DOM sibling (outside .filter-dropdown) so position:fixed escapes
	     the .filter-bar overflow-x:auto clipping context. -->
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div
		bind:this={panelEl}
		class="filter-panel"
		style="top: {panelTop}px; left: {panelLeft}px;"
		onmouseenter={cancelClose}
		onmouseleave={handleLeave}
		onfocusin={handleFocusIn}
		onkeydown={handlePanelKeydown}
	>
		{@render children()}
	</div>
{/if}

<style>
	.filter-dropdown {
		position: relative;
	}

	.filter-trigger {
		display: inline-flex;
		align-items: center;
		gap: 0.35rem;
		padding: 0.45rem 0.85rem;
		background: var(--navy-700);
		border: 1px solid var(--border);
		border-radius: 999px;
		color: var(--text-secondary);
		font-size: 0.82rem;
		cursor: pointer;
		white-space: nowrap;
		transition: border-color 0.15s, color 0.15s;
	}

	.filter-trigger:hover,
	.filter-trigger.has-active {
		border-color: var(--amber);
		color: var(--text-primary);
	}

	.filter-badge {
		background: var(--amber);
		color: var(--navy-900);
		border-radius: 999px;
		min-width: 18px;
		height: 18px;
		font-size: 0.65rem;
		font-weight: 800;
		display: flex;
		align-items: center;
		justify-content: center;
		padding: 0 4px;
	}

	.chevron {
		transition: transform 0.15s;
	}

	.chevron.open {
		transform: rotate(180deg);
	}

	.filter-panel {
		position: fixed;
		z-index: 120;
		background: var(--navy-800);
		border: 1px solid var(--border);
		border-radius: var(--radius);
		padding: 0.75rem;
		min-width: 240px;
		max-width: 400px;
		max-height: 360px;
		overflow-y: auto;
		box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5);
	}
</style>

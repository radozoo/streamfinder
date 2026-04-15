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

	let open = $state(false);
	let pinned = $state(false);
	let closeTimer: ReturnType<typeof setTimeout> | null = null;

	function scheduleClose() {
		if (pinned) return;
		closeTimer = setTimeout(() => {
			if (!pinned) open = false;
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
		open = true;
	}

	function handleLeave() {
		scheduleClose();
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Enter' || e.key === ' ') {
			e.preventDefault();
			open = !open;
		} else if (e.key === 'Escape' && open) {
			open = false;
			pinned = false;
		}
	}

	function handleFocusIn() {
		cancelClose();
		pinned = true;
	}

	function handleFocusOut(e: FocusEvent) {
		const wrapper = (e.currentTarget as HTMLElement);
		// Only unpin if focus leaves the entire dropdown wrapper
		requestAnimationFrame(() => {
			if (!wrapper.contains(document.activeElement)) {
				pinned = false;
				scheduleClose();
			}
		});
	}
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
		class="filter-trigger"
		class:has-active={activeCount > 0}
		aria-expanded={open}
		aria-haspopup="true"
		onkeydown={handleKeydown}
	>
		{label}
		{#if activeCount > 0}
			<span class="filter-badge">{activeCount}</span>
		{/if}
		<svg class="chevron" class:open width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="6 9 12 15 18 9"/></svg>
	</button>

	{#if open}
		<div class="filter-panel">
			{@render children()}
		</div>
	{/if}
</div>

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
		position: absolute;
		top: calc(100% + 6px);
		left: 0;
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

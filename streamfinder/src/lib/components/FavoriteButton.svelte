<script lang="ts">
	import { favorites } from '$lib/favorites.svelte';

	let {
		csfdId,
		size = 'card',
		label
	}: {
		csfdId: number | null | undefined;
		/** 'card' overlays the poster; 'action' sits in the detail page's button row. */
		size?: 'card' | 'action';
		label?: string;
	} = $props();

	let isFav = $derived(favorites.has(csfdId));

	function onclick(e: MouseEvent) {
		// On a card this button sits on top of a link. Without both of these the click
		// navigates to the title instead of hearting it.
		e.preventDefault();
		e.stopPropagation();
		favorites.toggle(csfdId);
	}
</script>

{#if csfdId != null}
	<button
		class="fav-btn {size}"
		class:on={isFav}
		type="button"
		{onclick}
		aria-pressed={isFav}
		aria-label={isFav ? 'Odebrat z oblíbených' : 'Přidat do oblíbených'}
		title={isFav ? 'Odebrat z oblíbených' : 'Přidat do oblíbených'}
	>
		<svg viewBox="0 0 24 24" aria-hidden="true">
			<path
				d="M12 20s-7-4.4-9.5-9C.5 7.3 2.7 4 6 4c2 0 3.4 1 4 2.2C10.6 5 12 4 14 4c3.3 0 5.5 3.3 3.5 7-2.5 4.6-9.5 9-9.5 9z"
			/>
		</svg>
		{#if label}<span>{isFav ? 'V oblíbených' : label}</span>{/if}
	</button>
{/if}

<style>
	.fav-btn {
		display: inline-flex;
		align-items: center;
		gap: 0.4rem;
		cursor: pointer;
		color: #fff;
		background: rgba(8, 14, 30, 0.72);
		border: 1px solid var(--border);
		backdrop-filter: blur(4px);
		transition: color 0.15s, background 0.15s, transform 0.15s;
	}

	.fav-btn svg {
		width: 18px;
		height: 18px;
		fill: none;
		stroke: currentColor;
		stroke-width: 1.8;
		stroke-linejoin: round;
	}

	/* Overlay on a poster: bottom-left, the only corner still free. Type sits top-left,
	   "beží" and the S·E marker top-right, the platform bottom-right — so the heart
	   needs no badge to move out of its way. */
	.fav-btn.card {
		position: absolute;
		bottom: 0.4rem;
		left: 0.4rem;
		z-index: 3;
		padding: 5px;
		border-radius: 999px;
	}

	.fav-btn.action {
		padding: 0.6rem 1rem;
		border-radius: var(--radius-sm);
		font: inherit;
		font-size: 0.85rem;
		font-weight: 600;
		background: var(--navy-700);
	}

	.fav-btn:hover {
		color: #fb7185;
		transform: scale(1.06);
	}

	.fav-btn.on {
		color: #f43f5e;
	}

	.fav-btn.on svg {
		fill: #f43f5e;
	}

	.fav-btn:focus-visible {
		outline: 2px solid var(--amber);
		outline-offset: 2px;
	}

	@media (prefers-reduced-motion: reduce) {
		.fav-btn {
			transition: none;
		}
		.fav-btn:hover {
			transform: none;
		}
	}
</style>

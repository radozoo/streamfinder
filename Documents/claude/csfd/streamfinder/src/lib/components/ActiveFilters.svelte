<script lang="ts">
	let {
		filters,
		onRemove,
		onClearAll
	}: {
		filters: { category: string; value: string }[];
		onRemove: (category: string, value: string) => void;
		onClearAll: () => void;
	} = $props();
</script>

{#if filters.length > 0}
	<div class="active-filters">
		{#each filters as f}
			<span class="active-chip">
				<span class="chip-category">{f.category}:</span>
				{f.value}
				<button class="chip-remove" onclick={() => onRemove(f.category, f.value)} aria-label="Odebrat filtr {f.value}">×</button>
			</span>
		{/each}
		<button class="clear-all-btn" onclick={onClearAll}>Zrušit vše</button>
	</div>
{/if}

<style>
	.active-filters {
		display: flex;
		flex-wrap: wrap;
		gap: 0.35rem;
		align-items: center;
		margin-bottom: 1rem;
	}

	.active-chip {
		display: inline-flex;
		align-items: center;
		gap: 0.25rem;
		padding: 3px 10px;
		background: var(--navy-600);
		border-radius: 999px;
		font-size: 0.75rem;
		color: var(--text-secondary);
	}

	.chip-category {
		color: var(--text-muted);
		font-size: 0.65rem;
		text-transform: uppercase;
		letter-spacing: 0.04em;
	}

	.chip-remove {
		background: none;
		border: none;
		color: var(--text-muted);
		font-size: 0.85rem;
		cursor: pointer;
		padding: 0;
		line-height: 1;
	}

	.chip-remove:hover {
		color: var(--amber);
	}

	.clear-all-btn {
		background: none;
		border: none;
		color: var(--text-muted);
		font-size: 0.72rem;
		cursor: pointer;
		padding: 3px 6px;
		text-decoration: underline;
		text-underline-offset: 2px;
	}

	.clear-all-btn:hover {
		color: var(--amber);
	}
</style>

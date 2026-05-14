<script lang="ts">
	let {
		items,
		selected = [],
		onToggle
	}: {
		items: { name: string; count?: number; hit?: boolean }[];
		selected: string[];
		onToggle: (name: string) => void;
	} = $props();
</script>

<div class="pill-grid">
	{#each items as item}
		<button
			class="pill"
			class:active={selected.includes(item.name)}
			class:disabled={item.hit === false && !selected.includes(item.name)}
			onclick={() => onToggle(item.name)}
		>
			{item.name}
			{#if item.count !== undefined}
				<span class="pill-count">{item.count}</span>
			{/if}
		</button>
	{/each}
</div>

<style>
	.pill-grid {
		display: flex;
		flex-wrap: wrap;
		gap: 0.35rem;
	}

	.pill-count {
		font-size: 0.65rem;
		color: var(--text-muted);
		margin-left: 2px;
	}

	.pill.active .pill-count {
		color: var(--navy-900);
		opacity: 0.7;
	}
</style>

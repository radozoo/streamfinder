<script lang="ts">
	let {
		items,
		selected = [],
		onSelect,
		onRemove,
		placeholder = 'Hledat…',
		formatItem,
		loading = false
	}: {
		items: { name: string; role?: string; count?: number }[];
		selected: string[];
		onSelect: (name: string) => void;
		onRemove: (name: string) => void;
		placeholder?: string;
		formatItem?: (item: { name: string; role?: string; count?: number }) => string;
		loading?: boolean;
	} = $props();

	let query = $state('');
	let debounced = $state('');
	let timer: ReturnType<typeof setTimeout> | null = null;

	$effect(() => {
		if (timer) clearTimeout(timer);
		const q = query;
		timer = setTimeout(() => {
			debounced = q;
		}, 150);
	});

	let results = $derived.by(() => {
		const q = debounced.trim().toLowerCase();
		if (!q) return [];
		return items
			.filter((item) => item.name.toLowerCase().includes(q) && !selected.includes(item.name))
			.slice(0, 20);
	});

	function format(item: { name: string; role?: string; count?: number }): string {
		if (formatItem) return formatItem(item);
		return item.name;
	}
</script>

<div class="autocomplete">
	{#if selected.length > 0}
		<div class="selected-pills">
			{#each selected as name}
				<span class="selected-pill">
					{name}
					<button class="pill-remove" onclick={() => onRemove(name)} aria-label="Odebrat {name}">×</button>
				</span>
			{/each}
		</div>
	{/if}

	<input
		class="autocomplete-input"
		type="text"
		{placeholder}
		bind:value={query}
	/>

	{#if loading}
		<div class="autocomplete-loading">Načítání…</div>
	{:else if debounced.trim() && results.length === 0}
		<div class="autocomplete-empty">Žádné výsledky</div>
	{:else if results.length > 0}
		<div class="autocomplete-results">
			{#each results as item}
				<button class="autocomplete-item" onclick={() => { onSelect(item.name); query = ''; debounced = ''; }}>
					{format(item)}
				</button>
			{/each}
		</div>
	{/if}
</div>

<style>
	.autocomplete {
		display: flex;
		flex-direction: column;
		gap: 0.4rem;
	}

	.selected-pills {
		display: flex;
		flex-wrap: wrap;
		gap: 0.3rem;
	}

	.selected-pill {
		display: inline-flex;
		align-items: center;
		gap: 0.25rem;
		padding: 2px 8px;
		background: var(--amber);
		color: var(--navy-900);
		border-radius: 999px;
		font-size: 0.75rem;
		font-weight: 600;
	}

	.pill-remove {
		background: none;
		border: none;
		color: var(--navy-900);
		font-size: 0.9rem;
		cursor: pointer;
		padding: 0;
		line-height: 1;
		opacity: 0.6;
	}

	.pill-remove:hover {
		opacity: 1;
	}

	.autocomplete-input {
		width: 100%;
		background: var(--navy-700);
		border: 1px solid var(--border);
		border-radius: var(--radius-sm);
		padding: 0.4rem 0.6rem;
		color: var(--text-primary);
		font-size: 0.82rem;
		outline: none;
	}

	.autocomplete-input:focus {
		border-color: var(--amber);
	}

	.autocomplete-results {
		display: flex;
		flex-direction: column;
		max-height: 200px;
		overflow-y: auto;
	}

	.autocomplete-item {
		display: block;
		width: 100%;
		text-align: left;
		background: none;
		border: none;
		padding: 0.35rem 0.5rem;
		color: var(--text-secondary);
		font-size: 0.8rem;
		cursor: pointer;
		border-radius: var(--radius-sm);
	}

	.autocomplete-item:hover {
		background: var(--navy-600);
		color: var(--text-primary);
	}

	.autocomplete-loading,
	.autocomplete-empty {
		color: var(--text-muted);
		font-size: 0.78rem;
		padding: 0.5rem;
		text-align: center;
	}
</style>

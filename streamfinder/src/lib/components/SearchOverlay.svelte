<script lang="ts">
	import type { TitleIndex } from '$lib/types';
	import { base } from '$app/paths';
	import { fold, getSearchIndex, matchedName, matchesQuery, rankHit } from '$lib/search';

	interface Props {
		titles: TitleIndex[];
		onclose: () => void;
	}

	let { titles, onclose }: Props = $props();

	let query = $state('');

	// The field must take keystrokes the moment the overlay opens. The `autofocus`
	// attribute does not deliver that: browsers honour it when a document loads, not
	// when an element is inserted into a live one, so focus stayed on the lupa button
	// that opened this and the first thing typed went nowhere. Focusing explicitly
	// once the node exists is the only reliable way.
	let inputEl = $state<HTMLInputElement | null>(null);
	$effect(() => {
		inputEl?.focus();
	});

	const MAX_RESULTS = 8;

	let results = $derived.by(() => {
		const q = fold(query.trim());
		if (!q) return [];
		// Built on the first keystroke, then reused — see getSearchIndex.
		const index = getSearchIndex(titles);
		const hits = titles.filter((t) => matchesQuery(index, t, q));
		// With only 8 slots, index order (newest release first) answered "squid game"
		// with two making-of documentaries and pushed the series itself to fourth.
		hits.sort(
			(a, b) => rankHit(a, q) - rankHit(b, q) || (b.votes_count ?? 0) - (a.votes_count ?? 0)
		);
		return hits.slice(0, MAX_RESULTS).map((t) => ({ t, matched: matchedName(t, q) }));
	});

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Escape') onclose();
	}

	function ratingClass(r: number | null) {
		return r ? 'rating-good' : '';
	}
</script>

<div
	class="overlay-backdrop"
	onclick={onclose}
	onkeydown={(e) => e.key === 'Escape' && onclose()}
	role="presentation"
	tabindex="-1"
>
	<div
		class="overlay-panel"
		onclick={(e) => e.stopPropagation()}
		role="search"
		aria-label="Hledat tituly"
	>
		<div class="search-row">
			<svg class="search-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
				<circle cx="11" cy="11" r="8" /><path d="m21 21-4.3-4.3" />
			</svg>
			<input
				bind:this={inputEl}
				bind:value={query}
				onkeydown={handleKeydown}
				class="search-field"
				type="search"
				placeholder="Hledat film, seriál…"
				autocomplete="off"
			/>
			<button class="close-btn" onclick={onclose} aria-label="Zavřít">✕</button>
		</div>

		{#if results.length > 0}
			<ul class="results-list">
				{#each results as { t, matched } (t.id)}
					<li>
						<a class="result-item" href="{base}/titul/{t.id}/{t.slug}" onclick={onclose}>
							{#if t.poster}
								<img class="result-poster" src={t.poster} alt={t.title} loading="lazy" />
							{:else}
								<div class="result-poster result-poster--placeholder"></div>
							{/if}
							<div class="result-info">
								<span class="result-title">{t.title}</span>
								{#if matched}
									<span class="result-alt">{matched}</span>
								{/if}
								<span class="result-meta">
									{#if t.year}{t.year}{/if}
									{#if t.rating !== null}
										<span class={ratingClass(t.rating)}> · {t.rating} %</span>
									{/if}
									{#if t.platforms.length}
										<span class="result-platform"> · {t.platforms[0]}</span>
									{/if}
								</span>
							</div>
						</a>
					</li>
				{/each}
			</ul>
		{:else if query.trim()}
			<p class="no-results">Žádné výsledky pro „{query.trim()}"</p>
		{/if}
	</div>
</div>

<style>
	.overlay-backdrop {
		position: fixed;
		inset: 0;
		background: rgba(0, 0, 0, 0.7);
		backdrop-filter: blur(8px);
		z-index: 300;
		display: flex;
		justify-content: center;
		padding-top: 10vh;
	}

	.overlay-panel {
		background: var(--navy-800);
		border: 1px solid var(--border);
		border-radius: var(--radius);
		width: 100%;
		max-width: 560px;
		height: fit-content;
		max-height: 80vh;
		overflow-y: auto;
		box-shadow: 0 24px 80px rgba(0, 0, 0, 0.6);
	}

	.search-row {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		padding: 1rem 1.25rem;
		border-bottom: 1px solid var(--border);
	}

	.search-icon {
		color: var(--text-muted);
		flex-shrink: 0;
	}

	.search-field {
		flex: 1;
		background: none;
		border: none;
		outline: none;
		color: var(--text-primary);
		font-size: 1.05rem;
		font-family: inherit;
	}

	.search-field::placeholder {
		color: var(--text-muted);
	}

	.close-btn {
		background: none;
		border: none;
		color: var(--text-muted);
		cursor: pointer;
		font-size: 0.9rem;
		padding: 0.25rem;
		flex-shrink: 0;
	}

	.close-btn:hover {
		color: var(--text-primary);
	}

	.results-list {
		list-style: none;
		padding: 0.5rem 0;
	}

	.result-item {
		display: flex;
		align-items: center;
		gap: 0.9rem;
		padding: 0.6rem 1.25rem;
		transition: background 0.15s;
		text-decoration: none;
	}

	.result-item:hover {
		background: var(--navy-700);
	}

	.result-poster {
		width: 36px;
		height: 54px;
		border-radius: 4px;
		object-fit: cover;
		flex-shrink: 0;
	}

	.result-poster--placeholder {
		background: var(--navy-600);
	}

	.result-info {
		display: flex;
		flex-direction: column;
		gap: 0.2rem;
		min-width: 0;
	}

	.result-title {
		font-size: 0.95rem;
		font-weight: 600;
		color: var(--text-primary);
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}

	.result-alt {
		font-size: 0.8rem;
		color: var(--text-secondary, var(--text-muted));
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}

	.result-meta {
		font-size: 0.78rem;
		color: var(--text-muted);
	}

	.result-platform {
		color: var(--text-muted);
	}

	.no-results {
		padding: 1.5rem 1.25rem;
		color: var(--text-muted);
		font-size: 0.9rem;
	}
</style>

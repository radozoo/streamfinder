<script lang="ts">
	import type { PageData } from './$types';
	import type { TitleIndex, TitleDetail } from '$lib/types';
	import PosterCard from '$lib/components/PosterCard.svelte';
	import TitleModal from '$lib/components/TitleModal.svelte';
	import { base } from '$app/paths';
	import { untrack } from 'svelte';

	let { data }: { data: PageData } = $props();

	const PAGE_SIZE = 48;

	// snapshot of initial URL filter state — untrack so $state initialization
	// doesn't accidentally subscribe to the reactive `data` prop
	const snap = untrack(() => data);

	// ── Filter state ──────────────────────────────────────────────────────────
	let searchQuery = $state(snap.initialQuery ?? '');
	let selectedGenres = $state<string[]>(snap.initialGenres ?? []);
	let selectedPlatforms = $state<string[]>(snap.initialPlatforms ?? []);
	let selectedCountries = $state<string[]>(snap.initialCountries ?? []);
	let selectedTags = $state<string[]>(snap.initialTags ?? []);
	let selectedType = $state<string>(snap.initialType ?? '');
	let yearFrom = $state<number | ''>(snap.initialYearFrom ?? '');
	let yearTo = $state<number | ''>(snap.initialYearTo ?? '');
	let ratingMin = $state<number | ''>(snap.initialRatingMin ?? '');
	let sortBy = $state<'rating' | 'year' | 'vod_date' | 'votes'>(snap.initialSort ?? 'vod_date');

	// ── Pagination ───────────────────────────────────────────────────────────
	let page = $state(1);

	// ── Mobile filter sheet ──────────────────────────────────────────────────
	let filterPanelOpen = $state(false);

	// ── Modal state ───────────────────────────────────────────────────────────
	let modalTitle = $state<TitleDetail | null>(null);
	let modalLoading = $state(false);
	let detailCache: Record<string, TitleDetail> | null = null;

	// ── Filtered + sorted titles ──────────────────────────────────────────────
	let filtered = $derived.by(() => {
		const q = searchQuery.trim().toLowerCase();
		return data.titles
			.filter((t) => {
				if (
					q &&
					!t.title.toLowerCase().includes(q) &&
					!(t.title_en ?? '').toLowerCase().includes(q)
				)
					return false;
				if (selectedGenres.length && !selectedGenres.some((g) => t.genres.includes(g)))
					return false;
				if (selectedPlatforms.length && !selectedPlatforms.some((p) => t.platforms.includes(p)))
					return false;
				if (selectedCountries.length && !selectedCountries.some((c) => t.countries.includes(c)))
					return false;
				if (selectedTags.length && !selectedTags.some((tag) => t.tags.includes(tag)))
					return false;
				if (selectedType && t.title_type !== selectedType) return false;
				if (yearFrom !== '' && (t.year ?? 0) < yearFrom) return false;
				if (yearTo !== '' && (t.year ?? 9999) > yearTo) return false;
				if (ratingMin !== '' && (t.rating ?? 0) < ratingMin) return false;
				return true;
			})
			.sort((a, b) => {
				if (sortBy === 'rating') return (b.rating ?? 0) - (a.rating ?? 0);
				if (sortBy === 'year') return (b.year ?? 0) - (a.year ?? 0);
				if (sortBy === 'votes') return (b.votes_count ?? 0) - (a.votes_count ?? 0);
				return (b.vod_date ?? '').localeCompare(a.vod_date ?? '');
			});
	});

	// Reset page when filters change
	$effect(() => {
		filtered;
		page = 1;
	});

	let displayedTitles = $derived(filtered.slice(0, page * PAGE_SIZE));
	let hasMore = $derived(filtered.length > page * PAGE_SIZE);

	// ── URL sync ──────────────────────────────────────────────────────────────
	$effect(() => {
		const params = new URLSearchParams();
		if (searchQuery.trim()) params.set('q', searchQuery.trim());
		if (selectedGenres.length) params.set('genre', selectedGenres.join(','));
		if (selectedPlatforms.length) params.set('platform', selectedPlatforms.join(','));
		if (selectedCountries.length) params.set('country', selectedCountries.join(','));
		if (selectedTags.length) params.set('tag', selectedTags.join(','));
		if (selectedType) params.set('type', selectedType);
		if (yearFrom !== '') params.set('yearFrom', String(yearFrom));
		if (yearTo !== '') params.set('yearTo', String(yearTo));
		if (ratingMin !== '') params.set('ratingMin', String(ratingMin));
		if (sortBy !== 'vod_date') params.set('sort', sortBy);
		const str = params.toString();
		history.replaceState(null, '', str ? '?' + str : location.pathname);
	});

	// ── Dimension pills available counts ─────────────────────────────────────
	let availableGenres = $derived(
		data.dimensions.genres.map((g) => ({
			...g,
			hit: filtered.some((t) => t.genres.includes(g.name))
		}))
	);
	let availablePlatforms = $derived(
		data.dimensions.platforms.map((p) => ({
			...p,
			hit: filtered.some((t) => t.platforms.includes(p.name))
		}))
	);
	let availableCountries = $derived(
		data.dimensions.countries.slice(0, 12).map((c) => ({
			...c,
			hit: filtered.some((t) => t.countries.includes(c.name))
		}))
	);
	let availableTags = $derived(
		data.dimensions.tags.slice(0, 20).map((tag) => ({
			...tag,
			hit: filtered.some((t) => t.tags.includes(tag.name))
		}))
	);

	let typeOptions = $derived(
		['film', 'seriál', 'tv film', 'pořad', 'krátký film'].filter((type) =>
			data.titles.some((t) => t.title_type === type)
		)
	);

	// ── Helpers ───────────────────────────────────────────────────────────────
	function toggleGenre(name: string) {
		selectedGenres = selectedGenres.includes(name)
			? selectedGenres.filter((g) => g !== name)
			: [...selectedGenres, name];
	}
	function togglePlatform(name: string) {
		selectedPlatforms = selectedPlatforms.includes(name)
			? selectedPlatforms.filter((p) => p !== name)
			: [...selectedPlatforms, name];
	}
	function toggleCountry(name: string) {
		selectedCountries = selectedCountries.includes(name)
			? selectedCountries.filter((c) => c !== name)
			: [...selectedCountries, name];
	}
	function toggleTag(name: string) {
		selectedTags = selectedTags.includes(name)
			? selectedTags.filter((t) => t !== name)
			: [...selectedTags, name];
	}

	function clearAll() {
		searchQuery = '';
		selectedGenres = [];
		selectedPlatforms = [];
		selectedCountries = [];
		selectedTags = [];
		selectedType = '';
		yearFrom = '';
		yearTo = '';
		ratingMin = '';
		filterPanelOpen = false;
	}

	let hasFilters = $derived(
		searchQuery.trim() !== '' ||
			selectedGenres.length > 0 ||
			selectedPlatforms.length > 0 ||
			selectedCountries.length > 0 ||
			selectedTags.length > 0 ||
			selectedType !== '' ||
			yearFrom !== '' ||
			yearTo !== '' ||
			ratingMin !== ''
	);

	let activeFilterCount = $derived(
		(searchQuery.trim() ? 1 : 0) +
			selectedGenres.length +
			selectedPlatforms.length +
			selectedCountries.length +
			selectedTags.length +
			(selectedType ? 1 : 0) +
			(yearFrom !== '' ? 1 : 0) +
			(yearTo !== '' ? 1 : 0) +
			(ratingMin !== '' ? 1 : 0)
	);

	// ── Modal ─────────────────────────────────────────────────────────────────
	async function openModal(t: TitleIndex) {
		modalLoading = true;
		modalTitle = null;
		try {
			if (!detailCache) {
				const res = await fetch(`${base}/data/titles_detail.json`);
				detailCache = await res.json();
			}
			const key = `${t.id}-${t.slug}`;
			modalTitle = detailCache![key] ?? {
				...t,
				plot: null,
				backdrop: null,
				trailer_youtube_id: null,
				age_rating: null,
				directors: [],
				actors: [],
				screenwriters: [],
				cinematographers: [],
				composers: [],
				reviews: [],
				vods: []
			};
		} catch {
			modalTitle = {
				...t,
				plot: null,
				backdrop: null,
				trailer_youtube_id: null,
				age_rating: null,
				directors: [],
				actors: [],
				screenwriters: [],
				cinematographers: [],
				composers: [],
				reviews: [],
				vods: []
			};
		} finally {
			modalLoading = false;
		}
	}

	function closeModal() {
		modalTitle = null;
		modalLoading = false;
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Escape') filterPanelOpen = false;
	}
</script>

<svelte:window onkeydown={handleKeydown} />

<div class="page-container">
	<!-- Header row -->
	<div class="katalog-header">
		<h1 class="section-title">Katalog</h1>
		<div class="result-count">
			{filtered.length.toLocaleString('cs-CZ')}
			{filtered.length === 1 ? 'titul' : filtered.length < 5 ? 'tituly' : 'titulů'}
		</div>
	</div>

	<!-- Search + Sort bar -->
	<div class="search-bar">
		<input
			class="search-input"
			type="search"
			placeholder="Hledat film, seriál…"
			bind:value={searchQuery}
		/>
		<select class="sort-select" bind:value={sortBy}>
			<option value="vod_date">Nejnovější na VOD</option>
			<option value="rating">Hodnocení</option>
			<option value="votes">Počet hodnocení</option>
			<option value="year">Rok výroby</option>
		</select>
	</div>

	<div class="katalog-body">
		<!-- Sidebar filters (desktop) -->
		<aside class="sidebar">
			{#if hasFilters}
				<button class="clear-btn" onclick={clearAll}>✕ Zrušit filtry</button>
			{/if}

			<!-- Type -->
			<div class="filter-group">
				<h3 class="filter-label">Typ</h3>
				<div class="pill-group">
					{#each typeOptions as type}
						<button
							class="pill"
							class:active={selectedType === type}
							onclick={() => (selectedType = selectedType === type ? '' : type)}
						>
							{type}
						</button>
					{/each}
				</div>
			</div>

			<!-- Platforms -->
			<div class="filter-group">
				<h3 class="filter-label">Platforma</h3>
				<div class="pill-group">
					{#each availablePlatforms.slice(0, 12) as p}
						<button
							class="pill"
							class:active={selectedPlatforms.includes(p.name)}
							class:disabled={!p.hit && !selectedPlatforms.includes(p.name)}
							onclick={() => togglePlatform(p.name)}
						>
							{p.name}
						</button>
					{/each}
				</div>
			</div>

			<!-- Genres -->
			<div class="filter-group">
				<h3 class="filter-label">Žánr</h3>
				<div class="pill-group">
					{#each availableGenres.slice(0, 20) as g}
						<button
							class="pill"
							class:active={selectedGenres.includes(g.name)}
							class:disabled={!g.hit && !selectedGenres.includes(g.name)}
							onclick={() => toggleGenre(g.name)}
						>
							{g.name}
						</button>
					{/each}
				</div>
			</div>

			<!-- Countries -->
			{#if data.dimensions.countries.length > 0}
				<div class="filter-group">
					<h3 class="filter-label">Země</h3>
					<div class="pill-group">
						{#each availableCountries as c}
							<button
								class="pill"
								class:active={selectedCountries.includes(c.name)}
								class:disabled={!c.hit && !selectedCountries.includes(c.name)}
								onclick={() => toggleCountry(c.name)}
							>
								{c.name}
							</button>
						{/each}
					</div>
				</div>
			{/if}

			<!-- Tags -->
			{#if data.dimensions.tags.length > 0}
				<div class="filter-group">
					<h3 class="filter-label">Tagy</h3>
					<div class="pill-group">
						{#each availableTags as tag}
							<button
								class="pill"
								class:active={selectedTags.includes(tag.name)}
								class:disabled={!tag.hit && !selectedTags.includes(tag.name)}
								onclick={() => toggleTag(tag.name)}
							>
								{tag.name}
							</button>
						{/each}
					</div>
				</div>
			{/if}

			<!-- Year range -->
			<div class="filter-group">
				<h3 class="filter-label">Rok výroby</h3>
				<div class="year-range">
					<input
						class="num-input"
						type="number"
						placeholder="Od"
						min="1900"
						max="2030"
						bind:value={yearFrom}
					/>
					<span>–</span>
					<input
						class="num-input"
						type="number"
						placeholder="Do"
						min="1900"
						max="2030"
						bind:value={yearTo}
					/>
				</div>
			</div>

			<!-- Min rating -->
			<div class="filter-group">
				<h3 class="filter-label">Min. hodnocení</h3>
				<div class="year-range">
					<input
						class="num-input"
						type="number"
						placeholder="0"
						min="0"
						max="100"
						bind:value={ratingMin}
					/>
					<span>%</span>
				</div>
			</div>
		</aside>

		<!-- Poster grid -->
		<section class="grid-area">
			{#if filtered.length === 0}
				<div class="empty-state">
					<p>Žádné tituly nevyhovují filtrům.</p>
					<button class="clear-btn" onclick={clearAll}>Zrušit filtry</button>
				</div>
			{:else}
				<div class="poster-grid">
					{#each displayedTitles as title (title.id)}
						<PosterCard {title} onclick={openModal} />
					{/each}
				</div>

				{#if hasMore}
					<div class="load-more-row">
						<button class="load-more-btn" onclick={() => page++}>
							Načíst další
							<span class="load-more-count">({filtered.length - displayedTitles.length} zbývá)</span>
						</button>
					</div>
				{/if}
			{/if}
		</section>
	</div>
</div>

<!-- Mobile FAB -->
<button
	class="filter-fab"
	onclick={() => (filterPanelOpen = true)}
	aria-label="Otevřít filtry"
>
	<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
		<line x1="4" y1="6" x2="20" y2="6" />
		<line x1="8" y1="12" x2="20" y2="12" />
		<line x1="12" y1="18" x2="20" y2="18" />
	</svg>
	Filtrovat
	{#if activeFilterCount > 0}
		<span class="fab-badge">{activeFilterCount}</span>
	{/if}
</button>

<!-- Mobile filter sheet -->
{#if filterPanelOpen}
	<div class="sheet-backdrop" onclick={() => (filterPanelOpen = false)} onkeydown={(e) => e.key === 'Escape' && (filterPanelOpen = false)} role="presentation" tabindex="-1">
		<div class="filter-sheet" onclick={(e) => e.stopPropagation()} role="dialog" aria-modal="true" aria-label="Filtry" tabindex="-1">
			<div class="sheet-header">
				<h2 class="sheet-title">Filtry</h2>
				{#if hasFilters}
					<button class="clear-btn" onclick={clearAll}>Zrušit filtry</button>
				{/if}
				<button class="sheet-close" onclick={() => (filterPanelOpen = false)} aria-label="Zavřít">✕</button>
			</div>

			<div class="sheet-body">
				<!-- Type -->
				<div class="filter-group">
					<h3 class="filter-label">Typ</h3>
					<div class="pill-group">
						{#each typeOptions as type}
							<button
								class="pill"
								class:active={selectedType === type}
								onclick={() => (selectedType = selectedType === type ? '' : type)}
							>
								{type}
							</button>
						{/each}
					</div>
				</div>

				<!-- Platforms -->
				<div class="filter-group">
					<h3 class="filter-label">Platforma</h3>
					<div class="pill-group">
						{#each availablePlatforms.slice(0, 12) as p}
							<button
								class="pill"
								class:active={selectedPlatforms.includes(p.name)}
								class:disabled={!p.hit && !selectedPlatforms.includes(p.name)}
								onclick={() => togglePlatform(p.name)}
							>
								{p.name}
							</button>
						{/each}
					</div>
				</div>

				<!-- Genres -->
				<div class="filter-group">
					<h3 class="filter-label">Žánr</h3>
					<div class="pill-group">
						{#each availableGenres.slice(0, 20) as g}
							<button
								class="pill"
								class:active={selectedGenres.includes(g.name)}
								class:disabled={!g.hit && !selectedGenres.includes(g.name)}
								onclick={() => toggleGenre(g.name)}
							>
								{g.name}
							</button>
						{/each}
					</div>
				</div>

				<!-- Countries -->
				{#if data.dimensions.countries.length > 0}
					<div class="filter-group">
						<h3 class="filter-label">Země</h3>
						<div class="pill-group">
							{#each availableCountries as c}
								<button
									class="pill"
									class:active={selectedCountries.includes(c.name)}
									class:disabled={!c.hit && !selectedCountries.includes(c.name)}
									onclick={() => toggleCountry(c.name)}
								>
									{c.name}
								</button>
							{/each}
						</div>
					</div>
				{/if}

				<!-- Year range -->
				<div class="filter-group">
					<h3 class="filter-label">Rok výroby</h3>
					<div class="year-range">
						<input class="num-input" type="number" placeholder="Od" min="1900" max="2030" bind:value={yearFrom} />
						<span>–</span>
						<input class="num-input" type="number" placeholder="Do" min="1900" max="2030" bind:value={yearTo} />
					</div>
				</div>

				<!-- Min rating -->
				<div class="filter-group">
					<h3 class="filter-label">Min. hodnocení</h3>
					<div class="year-range">
						<input class="num-input" type="number" placeholder="0" min="0" max="100" bind:value={ratingMin} />
						<span>%</span>
					</div>
				</div>
			</div>

			<div class="sheet-footer">
				<button class="apply-btn" onclick={() => (filterPanelOpen = false)}>
					Zobrazit {filtered.length.toLocaleString('cs-CZ')} titulů
				</button>
			</div>
		</div>
	</div>
{/if}

<TitleModal title={modalTitle} loading={modalLoading} onclose={closeModal} />

<style>
	.katalog-header {
		display: flex;
		align-items: baseline;
		gap: 1rem;
		margin-bottom: 1.25rem;
	}

	.result-count {
		color: var(--text-muted);
		font-size: 0.9rem;
	}

	.search-bar {
		display: flex;
		gap: 0.75rem;
		margin-bottom: 1.5rem;
	}

	.search-input {
		flex: 1;
		background: var(--navy-700);
		border: 1px solid var(--border);
		border-radius: var(--radius);
		padding: 0.6rem 1rem;
		color: var(--text-primary);
		font-size: 0.95rem;
		outline: none;
	}

	.search-input:focus {
		border-color: var(--amber);
	}

	.sort-select {
		background: var(--navy-700);
		border: 1px solid var(--border);
		border-radius: var(--radius);
		padding: 0.6rem 0.9rem;
		color: var(--text-secondary);
		font-size: 0.85rem;
		cursor: pointer;
		outline: none;
	}

	.katalog-body {
		display: grid;
		grid-template-columns: 220px 1fr;
		gap: 2rem;
		align-items: start;
	}

	/* Sidebar */
	.sidebar {
		position: sticky;
		top: 72px;
		display: flex;
		flex-direction: column;
		gap: 1.25rem;
	}

	.filter-group {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}

	.filter-label {
		font-size: 0.7rem;
		font-weight: 700;
		letter-spacing: 0.08em;
		text-transform: uppercase;
		color: var(--text-muted);
	}

	.pill-group {
		display: flex;
		flex-wrap: wrap;
		gap: 0.4rem;
	}

	.year-range {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		color: var(--text-muted);
	}

	.num-input {
		width: 70px;
		background: var(--navy-700);
		border: 1px solid var(--border);
		border-radius: var(--radius-sm);
		padding: 0.35rem 0.5rem;
		color: var(--text-primary);
		font-size: 0.85rem;
		outline: none;
	}

	.clear-btn {
		background: none;
		border: 1px solid var(--border);
		border-radius: var(--radius-sm);
		padding: 0.4rem 0.75rem;
		color: var(--text-muted);
		font-size: 0.8rem;
		cursor: pointer;
		width: fit-content;
		transition: color 0.15s, border-color 0.15s;
	}

	.clear-btn:hover {
		color: var(--text-primary);
		border-color: var(--text-muted);
	}

	.poster-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
		gap: 1rem;
	}

	.empty-state {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 1rem;
		padding: 4rem 0;
		color: var(--text-muted);
	}

	/* Load more */
	.load-more-row {
		display: flex;
		justify-content: center;
		margin-top: 2rem;
	}

	.load-more-btn {
		background: var(--navy-700);
		border: 1px solid var(--border);
		border-radius: var(--radius);
		padding: 0.7rem 2rem;
		color: var(--text-secondary);
		font-size: 0.9rem;
		cursor: pointer;
		transition: border-color 0.15s, color 0.15s;
	}

	.load-more-btn:hover {
		border-color: var(--amber);
		color: var(--text-primary);
	}

	.load-more-count {
		color: var(--text-muted);
		font-size: 0.8rem;
		margin-left: 0.4rem;
	}

	/* Mobile FAB */
	.filter-fab {
		display: none;
		position: fixed;
		bottom: 1.5rem;
		left: 50%;
		transform: translateX(-50%);
		z-index: 50;
		background: var(--amber);
		color: var(--navy-900);
		border: none;
		border-radius: 999px;
		padding: 0.65rem 1.5rem;
		font-size: 0.9rem;
		font-weight: 700;
		cursor: pointer;
		gap: 0.4rem;
		align-items: center;
		box-shadow: 0 4px 20px rgba(0, 0, 0, 0.4);
	}

	.fab-badge {
		background: var(--navy-900);
		color: var(--amber);
		border-radius: 999px;
		width: 20px;
		height: 20px;
		font-size: 0.7rem;
		font-weight: 800;
		display: flex;
		align-items: center;
		justify-content: center;
	}

	/* Mobile bottom sheet */
	.sheet-backdrop {
		position: fixed;
		inset: 0;
		background: rgba(0, 0, 0, 0.6);
		z-index: 150;
		display: flex;
		align-items: flex-end;
	}

	.filter-sheet {
		width: 100%;
		background: var(--navy-800);
		border-radius: var(--radius) var(--radius) 0 0;
		border-top: 1px solid var(--border);
		max-height: 85vh;
		display: flex;
		flex-direction: column;
	}

	.sheet-header {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		padding: 1rem 1.25rem;
		border-bottom: 1px solid var(--border);
		flex-shrink: 0;
	}

	.sheet-title {
		font-family: 'Playfair Display', Georgia, serif;
		font-size: 1.1rem;
		font-weight: 700;
		flex: 1;
	}

	.sheet-close {
		background: none;
		border: none;
		color: var(--text-muted);
		font-size: 1rem;
		cursor: pointer;
		padding: 0.25rem;
	}

	.sheet-body {
		overflow-y: auto;
		padding: 1.25rem;
		display: flex;
		flex-direction: column;
		gap: 1.25rem;
		flex: 1;
	}

	.sheet-footer {
		padding: 1rem 1.25rem;
		border-top: 1px solid var(--border);
		flex-shrink: 0;
	}

	.apply-btn {
		width: 100%;
		background: var(--amber);
		color: var(--navy-900);
		border: none;
		border-radius: var(--radius);
		padding: 0.75rem;
		font-size: 0.95rem;
		font-weight: 700;
		cursor: pointer;
		transition: opacity 0.15s;
	}

	.apply-btn:hover {
		opacity: 0.9;
	}

	/* Responsive */
	@media (max-width: 900px) {
		.katalog-body {
			grid-template-columns: 1fr;
		}

		.sidebar {
			display: none;
		}

		.filter-fab {
			display: flex;
		}
	}

	@media (max-width: 640px) {
		.poster-grid {
			grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
		}
	}
</style>

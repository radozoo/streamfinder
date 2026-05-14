<script lang="ts">
	import type { PageData } from './$types';
	import type { TitleIndex, TitleDetail, CrewEntry } from '$lib/types';
	import PosterCard from '$lib/components/PosterCard.svelte';
	import TitleModal from '$lib/components/TitleModal.svelte';
	import FilterBar from '$lib/components/FilterBar.svelte';
	import ActiveFilters from '$lib/components/ActiveFilters.svelte';
	import PillGrid from '$lib/components/PillGrid.svelte';
	import AutocompleteDropdown from '$lib/components/AutocompleteDropdown.svelte';
	import RangeSlider from '$lib/components/RangeSlider.svelte';
	import { base } from '$app/paths';
	import { untrack } from 'svelte';
	import { loadCrewIndex, isCrewLoaded } from '$lib/data/crew';

	let { data }: { data: PageData } = $props();

	const PAGE_SIZE = 48;
	const YEAR_MIN = 1920;
	const YEAR_MAX = 2026;

	const snap = untrack(() => data);

	// ── Filter state ──────────────────────────────────────────────────────────
	let searchQuery = $state(snap.initialQuery ?? '');
	let selectedGenres = $state<string[]>(snap.initialGenres ?? []);
	let selectedPlatforms = $state<string[]>(snap.initialPlatforms ?? []);
	let selectedCountries = $state<string[]>(snap.initialCountries ?? []);
	let selectedTags = $state<string[]>(snap.initialTags ?? []);
	let selectedType = $state<string>(snap.initialType ?? '');
	let selectedCrew = $state<string[]>(snap.initialCrew ?? []);
	let yearFrom = $state<number>(snap.initialYearFrom ?? YEAR_MIN);
	let yearTo = $state<number>(snap.initialYearTo ?? YEAR_MAX);
	let ratingMin = $state<number>(snap.initialRatingMin ?? 0);
	let sortBy = $state<'rating' | 'year' | 'vod_date' | 'votes'>(snap.initialSort ?? 'vod_date');

	// ── Pagination ───────────────────────────────────────────────────────────
	let page = $state(1);

	// ── Mobile filter sheet ──────────────────────────────────────────────────
	let filterPanelOpen = $state(false);

	// ── Modal state ───────────────────────────────────────────────────────────
	let modalTitle = $state<TitleDetail | null>(null);
	let modalLoading = $state(false);
	let detailCache: Record<string, TitleDetail> | null = null;

	// ── Crew lazy loading ────────────────────────────────────────────────────
	let crewItems = $state<CrewEntry[]>([]);
	let crewLoading = $state(false);
	let crewIdToName: Map<number, string> | null = null;

	async function ensureCrewLoaded() {
		if (isCrewLoaded()) return;
		if (crewLoading) return;
		crewLoading = true;
		try {
			const list = await loadCrewIndex();
			crewItems = list;
			crewIdToName = new Map(list.map((c) => [c.id, c.name]));
		} finally {
			crewLoading = false;
		}
	}

	// If initial URL has crew params, load crew data immediately
	if (snap.initialCrew && snap.initialCrew.length > 0) {
		ensureCrewLoaded();
	}

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
				if (yearFrom > YEAR_MIN && (t.year ?? 0) < yearFrom) return false;
				if (yearTo < YEAR_MAX && (t.year ?? 9999) > yearTo) return false;
				if (ratingMin > 0 && (t.rating ?? 0) < ratingMin) return false;
				// Crew filter
				if (selectedCrew.length && crewIdToName) {
					const titleCrewNames = (t.crew_ids ?? []).map((id) => crewIdToName!.get(id)).filter(Boolean);
					if (!selectedCrew.some((name) => titleCrewNames.includes(name))) return false;
				}
				return true;
			})
			.sort((a, b) => {
				if (sortBy === 'rating') return (b.rating ?? 0) - (a.rating ?? 0);
				if (sortBy === 'year') return (b.year ?? 0) - (a.year ?? 0);
				if (sortBy === 'votes') return (b.votes_count ?? 0) - (a.votes_count ?? 0);
				return (b.vod_date ?? '').localeCompare(a.vod_date ?? '');
			});
	});

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
		for (const name of selectedCrew) params.append('crew', name);
		if (yearFrom > YEAR_MIN) params.set('yearFrom', String(yearFrom));
		if (yearTo < YEAR_MAX) params.set('yearTo', String(yearTo));
		if (ratingMin > 0) params.set('ratingMin', String(ratingMin));
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
		data.dimensions.countries.slice(0, 30).map((c) => ({
			...c,
			hit: filtered.some((t) => t.countries.includes(c.name))
		}))
	);
	let availableTags = $derived(
		data.dimensions.tags.slice(0, 50).map((tag) => ({
			...tag,
			hit: filtered.some((t) => t.tags.includes(tag.name))
		}))
	);

	let typeOptions = $derived(
		['film', 'seriál', 'tv film', 'pořad', 'krátký film'].filter((type) =>
			data.titles.some((t) => t.title_type === type)
		)
	);

	// ── Toggle helpers ────────────────────────────────────────────────────────
	function toggle(arr: string[], name: string): string[] {
		return arr.includes(name) ? arr.filter((v) => v !== name) : [...arr, name];
	}

	function clearAll() {
		searchQuery = '';
		selectedGenres = [];
		selectedPlatforms = [];
		selectedCountries = [];
		selectedTags = [];
		selectedType = '';
		selectedCrew = [];
		yearFrom = YEAR_MIN;
		yearTo = YEAR_MAX;
		ratingMin = 0;
		filterPanelOpen = false;
	}

	let hasFilters = $derived(
		searchQuery.trim() !== '' ||
			selectedGenres.length > 0 ||
			selectedPlatforms.length > 0 ||
			selectedCountries.length > 0 ||
			selectedTags.length > 0 ||
			selectedType !== '' ||
			selectedCrew.length > 0 ||
			yearFrom > YEAR_MIN ||
			yearTo < YEAR_MAX ||
			ratingMin > 0
	);

	let activeFilterCount = $derived(
		(searchQuery.trim() ? 1 : 0) +
			selectedGenres.length +
			selectedPlatforms.length +
			selectedCountries.length +
			selectedTags.length +
			(selectedType ? 1 : 0) +
			selectedCrew.length +
			(yearFrom > YEAR_MIN ? 1 : 0) +
			(yearTo < YEAR_MAX ? 1 : 0) +
			(ratingMin > 0 ? 1 : 0)
	);

	// ── Active filter chips ──────────────────────────────────────────────────
	let activeFilterList = $derived.by(() => {
		const chips: { category: string; value: string }[] = [];
		for (const g of selectedGenres) chips.push({ category: 'Žánr', value: g });
		for (const p of selectedPlatforms) chips.push({ category: 'Platforma', value: p });
		for (const c of selectedCountries) chips.push({ category: 'Krajina', value: c });
		for (const t of selectedTags) chips.push({ category: 'Tag', value: t });
		if (selectedType) chips.push({ category: 'Typ', value: selectedType });
		for (const c of selectedCrew) chips.push({ category: 'Tvůrce', value: c });
		if (yearFrom > YEAR_MIN || yearTo < YEAR_MAX) chips.push({ category: 'Rok', value: `${yearFrom}–${yearTo}` });
		if (ratingMin > 0) chips.push({ category: 'Hodnocení', value: `${ratingMin}%+` });
		return chips;
	});

	function removeFilter(category: string, value: string) {
		if (category === 'Žánr') selectedGenres = selectedGenres.filter((g) => g !== value);
		else if (category === 'Platforma') selectedPlatforms = selectedPlatforms.filter((p) => p !== value);
		else if (category === 'Krajina') selectedCountries = selectedCountries.filter((c) => c !== value);
		else if (category === 'Tag') selectedTags = selectedTags.filter((t) => t !== value);
		else if (category === 'Typ') selectedType = '';
		else if (category === 'Tvůrce') selectedCrew = selectedCrew.filter((c) => c !== value);
		else if (category === 'Rok') { yearFrom = YEAR_MIN; yearTo = YEAR_MAX; }
		else if (category === 'Hodnocení') ratingMin = 0;
	}

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
				plot: null, backdrop: null, trailer_youtube_id: null, age_rating: null,
				directors: [], actors: [], screenwriters: [], cinematographers: [], composers: [],
				reviews: [], vods: []
			};
		} catch {
			modalTitle = {
				...t,
				plot: null, backdrop: null, trailer_youtube_id: null, age_rating: null,
				directors: [], actors: [], screenwriters: [], cinematographers: [], composers: [],
				reviews: [], vods: []
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

	<!-- Horizontal filter bar (desktop) -->
	<div class="filter-bar-row">
		<FilterBar
			genres={availableGenres}
			platforms={availablePlatforms}
			countries={availableCountries}
			tags={availableTags}
			{typeOptions}
			{crewItems}
			{crewLoading}
			onCrewHover={ensureCrewLoaded}
			{selectedGenres}
			{selectedPlatforms}
			{selectedCountries}
			{selectedTags}
			{selectedType}
			{selectedCrew}
			{yearFrom}
			{yearTo}
			{ratingMin}
			yearMin={YEAR_MIN}
			yearMax={YEAR_MAX}
			onToggleGenre={(name) => (selectedGenres = toggle(selectedGenres, name))}
			onTogglePlatform={(name) => (selectedPlatforms = toggle(selectedPlatforms, name))}
			onToggleCountry={(name) => (selectedCountries = toggle(selectedCountries, name))}
			onToggleTag={(name) => (selectedTags = toggle(selectedTags, name))}
			onToggleType={(name) => (selectedType = selectedType === name ? '' : name)}
			onSelectCrew={(name) => (selectedCrew = [...selectedCrew, name])}
			onRemoveCrew={(name) => (selectedCrew = selectedCrew.filter((c) => c !== name))}
			onYearChange={(from, to) => { yearFrom = from; yearTo = to; }}
			onRatingChange={(from) => { ratingMin = from; }}
		/>
	</div>

	<!-- Active filter chips -->
	<ActiveFilters filters={activeFilterList} onRemove={removeFilter} onClearAll={clearAll} />

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
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div class="sheet-backdrop" onclick={() => (filterPanelOpen = false)} onkeydown={(e) => e.key === 'Escape' && (filterPanelOpen = false)} role="presentation" tabindex="-1">
		<!-- svelte-ignore a11y_no_static_element_interactions -->
		<div class="filter-sheet" onclick={(e) => e.stopPropagation()} role="dialog" aria-modal="true" aria-label="Filtry" tabindex="-1">
			<div class="sheet-header">
				<h2 class="sheet-title">Filtry</h2>
				{#if hasFilters}
					<button class="clear-btn" onclick={clearAll}>Zrušit filtry</button>
				{/if}
				<button class="sheet-close" onclick={() => (filterPanelOpen = false)} aria-label="Zavřít">&#x2715;</button>
			</div>

			<div class="sheet-body">
				<div class="filter-group">
					<h3 class="filter-label">Typ</h3>
					<PillGrid
						items={typeOptions.map((t) => ({ name: t, hit: true }))}
						selected={selectedType ? [selectedType] : []}
						onToggle={(name) => (selectedType = selectedType === name ? '' : name)}
					/>
				</div>

				<div class="filter-group">
					<h3 class="filter-label">Platforma</h3>
					<PillGrid items={availablePlatforms.slice(0, 12)} selected={selectedPlatforms} onToggle={(name) => (selectedPlatforms = toggle(selectedPlatforms, name))} />
				</div>

				<div class="filter-group">
					<h3 class="filter-label">Žánr</h3>
					<PillGrid items={availableGenres.slice(0, 20)} selected={selectedGenres} onToggle={(name) => (selectedGenres = toggle(selectedGenres, name))} />
				</div>

				{#if data.dimensions.countries.length > 0}
					<div class="filter-group">
						<h3 class="filter-label">Země</h3>
						<PillGrid items={availableCountries} selected={selectedCountries} onToggle={(name) => (selectedCountries = toggle(selectedCountries, name))} />
					</div>
				{/if}

				<div class="filter-group">
					<h3 class="filter-label">Tagy</h3>
					<AutocompleteDropdown
						items={availableTags}
						selected={selectedTags}
						onSelect={(name) => (selectedTags = toggle(selectedTags, name))}
						onRemove={(name) => (selectedTags = toggle(selectedTags, name))}
						placeholder="Hledat tagy…"
					/>
				</div>

				<div class="filter-group">
					<h3 class="filter-label">Tvůrci</h3>
					{#if !isCrewLoaded()}
						<button class="load-crew-btn" onclick={ensureCrewLoaded}>
							{crewLoading ? 'Načítání…' : 'Načíst tvůrce'}
						</button>
					{:else}
						<AutocompleteDropdown
							items={crewItems}
							selected={selectedCrew}
							onSelect={(name) => (selectedCrew = [...selectedCrew, name])}
							onRemove={(name) => (selectedCrew = selectedCrew.filter((c) => c !== name))}
							placeholder="Hledat herce, režiséry…"
							formatItem={(item) => `${item.name} (${item.role ?? ''}, ${item.count ?? ''})`}
						/>
					{/if}
				</div>

				<div class="filter-group">
					<h3 class="filter-label">Rok výroby</h3>
					<RangeSlider
						min={YEAR_MIN}
						max={YEAR_MAX}
						step={1}
						valueFrom={yearFrom}
						valueTo={yearTo}
						onChange={(from, to) => { yearFrom = from; yearTo = to; }}
					/>
				</div>

				<div class="filter-group">
					<h3 class="filter-label">Min. hodnocení</h3>
					<RangeSlider
						min={0}
						max={100}
						step={5}
						valueFrom={ratingMin}
						valueTo={100}
						onChange={(from) => { ratingMin = from; }}
						single
						suffix="%"
					/>
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
		margin-bottom: 1rem;
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

	.filter-bar-row {
		margin-bottom: 1rem;
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

	.load-crew-btn {
		background: var(--navy-700);
		border: 1px solid var(--border);
		border-radius: var(--radius-sm);
		padding: 0.5rem 1rem;
		color: var(--text-secondary);
		font-size: 0.82rem;
		cursor: pointer;
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

	@media (max-width: 640px) {
		.filter-fab {
			display: flex;
		}

		.poster-grid {
			grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
		}
	}
</style>

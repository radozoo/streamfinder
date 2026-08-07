<script lang="ts">
	import type { PageData } from './$types';
	import type { TitleIndex, CrewEntry } from '$lib/types';
	import PosterCard from '$lib/components/PosterCard.svelte';
	import FilterBar from '$lib/components/FilterBar.svelte';
	import MobileFilterSheet from '$lib/components/MobileFilterSheet.svelte';
	import ActiveFilters from '$lib/components/ActiveFilters.svelte';
	import PillGrid from '$lib/components/PillGrid.svelte';
	import AutocompleteDropdown from '$lib/components/AutocompleteDropdown.svelte';
	import RangeSlider from '$lib/components/RangeSlider.svelte';
	import { base } from '$app/paths';
	import { goto, afterNavigate } from '$app/navigation';
	import { fold } from '$lib/search';
	import { favorites } from '$lib/favorites.svelte';
	import { untrack } from 'svelte';
	import { browser } from '$app/environment';
	// Aliased: this file already has a `page` — the pagination counter.
	import { page as appPage } from '$app/state';
	import { katalogFilters, EMPTY_PARAMS } from '$lib/filter-params';
	import { loadCrewIndex, loadCrewTitles, isCrewLoaded } from '$lib/data/crew';

	let { data }: { data: PageData } = $props();

	const PAGE_SIZE = 48;
	const YEAR_MIN = 1920;
	const YEAR_MAX = 2026;

	// ── Filter state, seeded from the URL ─────────────────────────────────────
	// Read here rather than in load(): a load() that touches url.searchParams cannot
	// be prerendered, which is why this page used to answer with 404.html. On the
	// server there is no query string to read — the prerendered file is the unfiltered
	// page — and the browser seeds from the real URL on hydration.
	// untrack: seed once, then own the state. Without it a navigation that updates
	// `page` would reset every filter the visitor has set.
	const initial = untrack(() => katalogFilters(browser ? appPage.url.searchParams : EMPTY_PARAMS));

	let searchQuery = $state(initial.query);
	let selectedGenres = $state<string[]>(initial.genres);
	let selectedPlatforms = $state<string[]>(initial.platforms);
	let selectedCountries = $state<string[]>(initial.countries);
	let selectedTags = $state<string[]>(initial.tags);
	let selectedTypes = $state<string[]>(initial.types);
	let selectedCrew = $state<string[]>(initial.crew);
	let favoritesOnly = $state<boolean>(initial.favoritesOnly);
	let yearFrom = $state<number>(initial.yearFrom ?? YEAR_MIN);
	let yearTo = $state<number>(initial.yearTo ?? YEAR_MAX);
	let ratingMin = $state<number>(initial.ratingMin ?? 0);
	let recencyDays = $state<number>(initial.recency);
	let sortBy = $state<'rating' | 'year' | 'vod_date' | 'votes'>(initial.sort);

	// ── "Přidáno na VOD" recency presets ─────────────────────────────────────
	// Mutually exclusive windows → single-select. A work passes if its most recent
	// VOD activity is within the window; for serials that's the last episode date
	// (last_vod_date), so a running show with a fresh episode qualifies.
	const RECENCY_OPTIONS: { label: string; days: number }[] = [
		{ label: 'Vše', days: 0 },
		{ label: '7 dní', days: 7 },
		{ label: '30 dní', days: 30 },
		{ label: '3 měsíce', days: 90 },
		{ label: '6 měsíců', days: 180 },
		{ label: 'Rok', days: 365 },
		{ label: '2 roky', days: 730 },
		{ label: '3 roky', days: 1095 }
	];

	function recencyDate(t: TitleIndex): string {
		const own = t.vod_date ?? '';
		const last = t.last_vod_date ?? '';
		return own > last ? own : last; // ISO strings compare lexicographically
	}

	function cutoffISO(days: number): string {
		const d = new Date();
		d.setDate(d.getDate() - days);
		return d.toISOString().slice(0, 10);
	}

	function recencyLabel(days: number): string {
		return RECENCY_OPTIONS.find((o) => o.days === days)?.label ?? '';
	}

	// ── Pagination ───────────────────────────────────────────────────────────
	let page = $state(1);

	// ── Crew lazy loading ────────────────────────────────────────────────────
	let crewItems = $state<CrewEntry[]>([]);
	let crewLoading = $state(false);
	// $state, not plain lets. Both maps arrive asynchronously, and the grid is computed
	// before the fetch resolves — so unless assigning them re-runs the filter, landing
	// on a shared ?crew=… link silently shows the whole catalog. Measured with both as
	// plain lets: 34 527 titles instead of 20.
	//
	// One reactive signal is technically enough (either assignment re-runs the
	// predicate, which then reads both). They are both $state anyway, so the facet does
	// not quietly depend on which of the two happens to be declared reactive.
	let crewIdToName = $state<Map<number, string> | null>(null);
	let crewTitles = $state<Map<number, number[]> | null>(null);

	async function ensureCrewLoaded() {
		if (crewLoading) return;
		if (isCrewLoaded() && crewTitles) return;
		crewLoading = true;
		try {
			// The names feed the facet list, the map feeds the predicate — a crew filter
			// needs both, so they are fetched together.
			const [list, titles] = await Promise.all([loadCrewIndex(), loadCrewTitles()]);
			crewItems = list;
			crewIdToName = new Map(list.map((c) => [c.id, c.name]));
			crewTitles = titles;
		} finally {
			crewLoading = false;
		}
	}

	// Landing on a shared ?crew=… link: fetch the crew data straight away, or the grid
	// renders unfiltered.
	//
	// Only in the browser. This runs during component init, which also happens on the
	// server, and a relative fetch() there throws "Cannot call fetch eagerly during
	// server-side rendering" — hard enough to take the whole dev server down. It went
	// unnoticed because nothing ever cold-loaded a crew link, and because production
	// serves Katalóg client-only through the SPA fallback, so there is no SSR to crash.
	// It would surface the moment this route starts prerendering.
	if (browser && initial.crew.length > 0) {
		ensureCrewLoaded();
	}

	// ── Shared filter predicate ───────────────────────────────────────────────
	// `skip` names one dimension to ignore. The result grid uses skip='' (apply
	// everything); each facet computes its available options with its OWN dimension
	// skipped, so picking one platform doesn't grey out the rest — multi-select
	// within a dimension is OR, while different dimensions combine as AND.
	let filterConfig = $derived.by(() => ({
		q: fold(searchQuery.trim()),
		recencyCutoff: recencyDays > 0 ? cutoffISO(recencyDays) : '',
		genres: selectedGenres,
		platforms: selectedPlatforms,
		countries: selectedCountries,
		tags: selectedTags,
		types: selectedTypes,
		yearFrom,
		yearTo,
		ratingMin,
		crew: selectedCrew,
		favoritesOnly,
		crewNames: crewIdToName,
		crewTitles
	}));

	function passes(t: TitleIndex, f: typeof filterConfig, skip: string): boolean {
		// Katalóg shows works only — episodes/seasons roll up under their serial.
		if (t.is_toplevel === false) return false;
		// Favourites are not a facet — they never widen a result set, so they are not
		// skippable and take no part in the availability counts.
		if (f.favoritesOnly && !favorites.has(t.csfd_id)) return false;
		if (skip !== 'q' && f.q && !fold(t.title).includes(f.q) && !fold(t.title_en ?? '').includes(f.q))
			return false;
		if (skip !== 'recency' && f.recencyCutoff) {
			const rec = recencyDate(t);
			if (!rec || rec < f.recencyCutoff) return false;
		}
		if (skip !== 'genre' && f.genres.length && !f.genres.some((g) => t.genres.includes(g)))
			return false;
		if (skip !== 'platform' && f.platforms.length && !f.platforms.some((p) => t.platforms.includes(p)))
			return false;
		if (skip !== 'country' && f.countries.length && !f.countries.some((c) => t.countries.includes(c)))
			return false;
		if (skip !== 'tag' && f.tags.length && !f.tags.some((tag) => t.tags.includes(tag)))
			return false;
		// OR within the dimension, like every other multi-select facet.
		if (skip !== 'type' && f.types.length && !f.types.includes(t.title_type ?? '')) return false;
		if (skip !== 'year' && f.yearFrom > YEAR_MIN && (t.year ?? 0) < f.yearFrom) return false;
		if (skip !== 'year' && f.yearTo < YEAR_MAX && (t.year ?? 9999) > f.yearTo) return false;
		if (skip !== 'rating' && f.ratingMin > 0 && (t.rating ?? 0) < f.ratingMin) return false;
		if (skip !== 'crew' && f.crew.length && f.crewNames && f.crewTitles) {
			const names = (f.crewTitles.get(t.id) ?? []).map((id) => f.crewNames!.get(id)).filter(Boolean);
			if (!f.crew.some((name) => names.includes(name))) return false;
		}
		return true;
	}

	// ── Filtered + sorted titles ──────────────────────────────────────────────
	let filtered = $derived.by(() => {
		const f = filterConfig;
		return data.titles
			.filter((t) => passes(t, f, ''))
			.sort((a, b) => {
				if (sortBy === 'rating') return (b.rating ?? 0) - (a.rating ?? 0);
				if (sortBy === 'year') return (b.year ?? 0) - (a.year ?? 0);
				if (sortBy === 'votes') return (b.votes_count ?? 0) - (a.votes_count ?? 0);
				return (b.vod_date ?? '').localeCompare(a.vod_date ?? '');
			});
	});

	// Facet availability: apply every filter EXCEPT the facet's own dimension.
	let genreBase = $derived.by(() => data.titles.filter((t) => passes(t, filterConfig, 'genre')));
	let platformBase = $derived.by(() => data.titles.filter((t) => passes(t, filterConfig, 'platform')));
	let countryBase = $derived.by(() => data.titles.filter((t) => passes(t, filterConfig, 'country')));
	let tagBase = $derived.by(() => data.titles.filter((t) => passes(t, filterConfig, 'tag')));

	$effect(() => {
		filtered;
		page = 1;
	});

	let displayedTitles = $derived(filtered.slice(0, page * PAGE_SIZE));
	let hasMore = $derived(filtered.length > page * PAGE_SIZE);

	// goto() throws if the router has not initialised yet, and
	// this effect runs during mount — the throw broke the effect outright, so the
	// URL was never written and filters vanished on Back. afterNavigate fires once
	// the initial navigation is done, which is exactly when the router is ready.
	let routerReady = $state(false);
	afterNavigate(() => (routerReady = true));

	// ── URL sync ──────────────────────────────────────────────────────────────
	$effect(() => {
		const params = new URLSearchParams();
		if (searchQuery.trim()) params.set('q', searchQuery.trim());
		if (selectedGenres.length) params.set('genre', selectedGenres.join(','));
		if (selectedPlatforms.length) params.set('platform', selectedPlatforms.join(','));
		if (selectedCountries.length) params.set('country', selectedCountries.join(','));
		if (selectedTags.length) params.set('tag', selectedTags.join(','));
		if (selectedTypes.length) params.set('type', selectedTypes.join(','));
		if (favoritesOnly) params.set('fav', '1');
		for (const name of selectedCrew) params.append('crew', name);
		if (yearFrom > YEAR_MIN) params.set('yearFrom', String(yearFrom));
		if (yearTo < YEAR_MAX) params.set('yearTo', String(yearTo));
		if (ratingMin > 0) params.set('ratingMin', String(ratingMin));
		if (recencyDays > 0) params.set('added', String(recencyDays));
		if (sortBy !== 'vod_date') params.set('sort', sortBy);
		const str = params.toString();
		// Three APIs look right here and two are not:
		//   history.replaceState(null, ...) wipes the router's own history state, so
		//     Back stopped navigating at all;
		//   replaceState() from $app/navigation is for shallow routing — it stores
		//     `page.url.href` as the entry's URL, NOT the one you hand it, so the
		//     address bar showed the filters while the history entry did not, and
		//     Back restored an unfiltered page;
		//   goto() performs a real client-side navigation, which is what makes the
		//     filtered URL the thing Back returns to.
		// keepFocus keeps the search field from losing the caret mid-typing, noScroll
		// keeps the grid still, and replaceState avoids one history entry per keystroke.
		if (!routerReady) return; // deps are read above, so this still re-runs later
		const target = str ? '?' + str : location.pathname;
		// goto() is a real navigation, so firing it when nothing changed re-runs load
		// for no reason — and on mount, with no filters set, that is every page view.
		if (location.pathname + location.search === new URL(target, location.href).pathname
			+ new URL(target, location.href).search) return;
		goto(target, {
			replaceState: true,
			keepFocus: true,
			noScroll: true
		});
	});

	// ── Dimension pills available counts ─────────────────────────────────────
	// Each facet's `hit` is computed against the set that applies every OTHER
	// filter but not this dimension's own selection (see `passes`/`*Base`), so an
	// already-picked value never disables its siblings.
	let availableGenres = $derived(
		data.dimensions.genres.map((g) => ({
			...g,
			hit: genreBase.some((t) => t.genres.includes(g.name))
		}))
	);
	let availablePlatforms = $derived(
		data.dimensions.platforms.map((p) => ({
			...p,
			hit: platformBase.some((t) => t.platforms.includes(p.name))
		}))
	);
	let availableCountries = $derived(
		data.dimensions.countries.slice(0, 30).map((c) => ({
			...c,
			hit: countryBase.some((t) => t.countries.includes(c.name))
		}))
	);
	// Tags: the most frequent ones as a browsable pill cloud (with availability),
	// plus the full list for free search (2000+ tags — a top-N slice can't be
	// searched, so search must see them all).
	let popularTags = $derived(
		data.dimensions.tags.slice(0, 40).map((tag) => ({
			...tag,
			hit: tagBase.some((t) => t.tags.includes(tag.name))
		}))
	);
	let allTags = $derived(data.dimensions.tags);

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
		selectedTypes = [];
		favoritesOnly = false;
		selectedCrew = [];
		yearFrom = YEAR_MIN;
		yearTo = YEAR_MAX;
		ratingMin = 0;
		recencyDays = 0;
	}

	let hasFilters = $derived(
		searchQuery.trim() !== '' ||
			selectedGenres.length > 0 ||
			selectedPlatforms.length > 0 ||
			selectedCountries.length > 0 ||
			selectedTags.length > 0 ||
			selectedTypes.length > 0 ||
			favoritesOnly ||
			selectedCrew.length > 0 ||
			yearFrom > YEAR_MIN ||
			yearTo < YEAR_MAX ||
			ratingMin > 0 ||
			recencyDays > 0
	);

	let activeFilterCount = $derived(
		(searchQuery.trim() ? 1 : 0) +
			selectedGenres.length +
			selectedPlatforms.length +
			selectedCountries.length +
			selectedTags.length +
			selectedTypes.length +
			(favoritesOnly ? 1 : 0) +
			selectedCrew.length +
			(yearFrom > YEAR_MIN ? 1 : 0) +
			(yearTo < YEAR_MAX ? 1 : 0) +
			(ratingMin > 0 ? 1 : 0) +
			(recencyDays > 0 ? 1 : 0)
	);

	// ── Active filter chips ──────────────────────────────────────────────────
	let activeFilterList = $derived.by(() => {
		const chips: { category: string; value: string }[] = [];
		for (const g of selectedGenres) chips.push({ category: 'Žánr', value: g });
		for (const p of selectedPlatforms) chips.push({ category: 'Platforma', value: p });
		for (const c of selectedCountries) chips.push({ category: 'Krajina', value: c });
		for (const t of selectedTags) chips.push({ category: 'Tag', value: t });
		for (const ty of selectedTypes) chips.push({ category: 'Typ', value: ty });
		if (favoritesOnly) chips.push({ category: 'Oblíbené', value: 'jen oblíbené' });
		for (const c of selectedCrew) chips.push({ category: 'Tvůrce', value: c });
		if (yearFrom > YEAR_MIN || yearTo < YEAR_MAX) chips.push({ category: 'Rok', value: `${yearFrom}–${yearTo}` });
		if (ratingMin > 0) chips.push({ category: 'Hodnocení', value: `${ratingMin}%+` });
		if (recencyDays > 0) chips.push({ category: 'Přidáno', value: recencyLabel(recencyDays) });
		return chips;
	});

	function removeFilter(category: string, value: string) {
		if (category === 'Žánr') selectedGenres = selectedGenres.filter((g) => g !== value);
		else if (category === 'Platforma') selectedPlatforms = selectedPlatforms.filter((p) => p !== value);
		else if (category === 'Krajina') selectedCountries = selectedCountries.filter((c) => c !== value);
		else if (category === 'Tag') selectedTags = selectedTags.filter((t) => t !== value);
		else if (category === 'Typ') selectedTypes = selectedTypes.filter((ty) => ty !== value);
		else if (category === 'Oblíbené') favoritesOnly = false;
		else if (category === 'Tvůrce') selectedCrew = selectedCrew.filter((c) => c !== value);
		else if (category === 'Rok') { yearFrom = YEAR_MIN; yearTo = YEAR_MAX; }
		else if (category === 'Hodnocení') ratingMin = 0;
		else if (category === 'Přidáno') recencyDays = 0;
	}

</script>

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
		<select class="sort-select" aria-label="Řadit podle" bind:value={sortBy}>
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
			tags={allTags}
			tagsTop={popularTags}
			{typeOptions}
			{crewItems}
			{crewLoading}
			onCrewHover={ensureCrewLoaded}
			{selectedGenres}
			{selectedPlatforms}
			{selectedCountries}
			{selectedTags}
			{selectedTypes}
			{favoritesOnly}
			favoritesCount={favorites.count}
			onToggleFavoritesOnly={() => (favoritesOnly = !favoritesOnly)}
			{selectedCrew}
			{yearFrom}
			{yearTo}
			{ratingMin}
			yearMin={YEAR_MIN}
			yearMax={YEAR_MAX}
			recencyOptions={RECENCY_OPTIONS}
			{recencyDays}
			onRecencyChange={(days) => (recencyDays = days)}
			onToggleGenre={(name) => (selectedGenres = toggle(selectedGenres, name))}
			onTogglePlatform={(name) => (selectedPlatforms = toggle(selectedPlatforms, name))}
			onToggleCountry={(name) => (selectedCountries = toggle(selectedCountries, name))}
			onToggleTag={(name) => (selectedTags = toggle(selectedTags, name))}
			onToggleType={(name) => (selectedTypes = toggle(selectedTypes, name))}
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
					<PosterCard {title} />
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

<MobileFilterSheet
	genres={availableGenres}
	platforms={availablePlatforms}
	countries={availableCountries}
	tags={allTags}
	tagsTop={popularTags}
	{typeOptions}
	{crewItems}
	{crewLoading}
	crewLoaded={isCrewLoaded()}
	onLoadCrew={ensureCrewLoaded}
	{selectedGenres}
	{selectedPlatforms}
	{selectedCountries}
	{selectedTags}
	{selectedTypes}
	{selectedCrew}
	{yearFrom}
	{yearTo}
	{ratingMin}
	yearMin={YEAR_MIN}
	yearMax={YEAR_MAX}
	recencyOptions={RECENCY_OPTIONS}
	{recencyDays}
	onRecencyChange={(days) => (recencyDays = days)}
	onToggleGenre={(name) => (selectedGenres = toggle(selectedGenres, name))}
	onTogglePlatform={(name) => (selectedPlatforms = toggle(selectedPlatforms, name))}
	onToggleCountry={(name) => (selectedCountries = toggle(selectedCountries, name))}
	onToggleTag={(name) => (selectedTags = toggle(selectedTags, name))}
	onToggleType={(name) => (selectedTypes = toggle(selectedTypes, name))}
	onSelectCrew={(name) => (selectedCrew = [...selectedCrew, name])}
	onRemoveCrew={(name) => (selectedCrew = selectedCrew.filter((c) => c !== name))}
	onYearChange={(from, to) => { yearFrom = from; yearTo = to; }}
	onRatingChange={(from) => { ratingMin = from; }}
	{activeFilterCount}
	{hasFilters}
	onClearAll={clearAll}
	resultCount={filtered.length}
/>


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

	@media (max-width: 640px) {
		.poster-grid {
			grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
		}
	}
</style>

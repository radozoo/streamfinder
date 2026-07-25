<script lang="ts">
	import { untrack, tick } from 'svelte';
	import type { PageData } from './$types';
	import type { TitleIndex, TitleDetail, CrewEntry } from '$lib/types';
	import PosterCard from '$lib/components/PosterCard.svelte';
	import TitleModal from '$lib/components/TitleModal.svelte';
	import FilterBar from '$lib/components/FilterBar.svelte';
	import ActiveFilters from '$lib/components/ActiveFilters.svelte';
	import { base } from '$app/paths';
	import { fold } from '$lib/search';
	import { loadCrewIndex, isCrewLoaded } from '$lib/data/crew';

	let { data }: { data: PageData } = $props();

	// ── Date constants ────────────────────────────────────────────────────────
	const TODAY = new Date().toISOString().slice(0, 10);
	const MAX_DAYS = 365;
	const DEFAULT_DAYS = 28;

	const CS_MONTHS = ['ledna','února','března','dubna','května','června','července','srpna','září','října','listopadu','prosince'];
	const CS_DAYS = ['Neděle','Pondělí','Úterý','Středa','Čtvrtek','Pátek','Sobota'];

	// Order of title types within a single day; anything else falls after these.
	const TYPE_RANK: Record<string, number> = {
		'seriál': 0,
		'série': 1,
		'film': 2,
		'tv film': 3,
		'epizoda': 4
	};
	const typeRank = (t: TitleIndex) => TYPE_RANK[t.title_type ?? ''] ?? 5;

	function formatDateLabel(iso: string): { label: string; dayName: string } {
		const d = new Date(iso + 'T12:00:00');
		return {
			label: `${d.getDate()}. ${CS_MONTHS[d.getMonth()]} ${d.getFullYear()}`,
			dayName: CS_DAYS[d.getDay()]
		};
	}

	function dateRange(from: string, to: string): string[] {
		const dates: string[] = [];
		const cur = new Date(from + 'T12:00:00');
		const end = new Date(to + 'T12:00:00');
		while (cur <= end) {
			dates.push(cur.toISOString().slice(0, 10));
			cur.setDate(cur.getDate() + 1);
		}
		return dates.reverse(); // newest first
	}

	const YEAR_MIN = 1920;
	const YEAR_MAX = 2026;

	// ── Reactive state ────────────────────────────────────────────────────────
	// untrack: seed once from URL params, then manage locally.
	// Without untrack, SvelteKit navigation updating `data` would re-initialize state.
	let daysBack = $state<number>(untrack(() => data.initialDays));
	// Full filter set — identical to Katalog.
	let searchQuery = $state(untrack(() => data.initialQuery ?? ''));
	let selectedGenres = $state<string[]>(untrack(() => data.initialGenres ?? []));
	let selectedPlatforms = $state<string[]>(untrack(() => data.initialPlatforms ?? []));
	let selectedCountries = $state<string[]>(untrack(() => data.initialCountries ?? []));
	let selectedTags = $state<string[]>(untrack(() => data.initialTags ?? []));
	let selectedType = $state<string>(untrack(() => data.initialType ?? ''));
	let selectedCrew = $state<string[]>(untrack(() => data.initialCrew ?? []));
	let yearFrom = $state<number>(untrack(() => data.initialYearFrom ?? YEAR_MIN));
	let yearTo = $state<number>(untrack(() => data.initialYearTo ?? YEAR_MAX));
	let ratingMin = $state<number>(untrack(() => data.initialRatingMin ?? 0));
	let filterPanelOpen = $state(false);

	// ── Crew lazy loading (same as Katalog) ───────────────────────────────────
	let crewItems = $state<CrewEntry[]>([]);
	let crewLoading = $state(false);
	let crewIdToName = $derived(
		crewItems.length ? new Map(crewItems.map((c) => [c.id, c.name])) : null
	);

	async function ensureCrewLoaded() {
		if (isCrewLoaded() || crewLoading) return;
		crewLoading = true;
		try {
			crewItems = await loadCrewIndex();
		} finally {
			crewLoading = false;
		}
	}

	if (untrack(() => data.initialCrew)?.length) ensureCrewLoaded();

	let minDate = $derived.by(() => {
		const d = new Date();
		d.setDate(d.getDate() - daysBack);
		return d.toISOString().slice(0, 10);
	});

	let allDates = $derived(dateRange(minDate, TODAY));

	// ── URL sync (single source of truth: state → URL) ────────────────────────
	$effect(() => {
		const params = new URLSearchParams();
		if (daysBack !== DEFAULT_DAYS) params.set('days', String(daysBack));
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
		const qs = params.toString();
		history.replaceState(null, '', qs ? '?' + qs : location.pathname);
	});

	function loadMoreDays() {
		daysBack = Math.min(daysBack + 14, MAX_DAYS);
	}

	// ── Groups (split for performance) ────────────────────────────────────────
	interface DayGroup {
		date: string;
		label: string;
		dayName: string;
		titles: TitleIndex[];
		isToday: boolean;
	}

	// Layer 1 — rebuilds only when daysBack changes (slow O(n) data scan)
	let titlesInRange = $derived.by(() => {
		const map = new Map<string, TitleIndex[]>();
		for (const t of data.titles) {
			if (!t.vod_date || t.vod_date < minDate || t.vod_date > TODAY) continue;
			const arr = map.get(t.vod_date) ?? [];
			arr.push(t);
			map.set(t.vod_date, arr);
		}
		return map;
	});

	// Full filter predicate — identical facets to Katalog.
	function passesFilters(t: TitleIndex): boolean {
		const q = fold(searchQuery.trim());
		if (q && !fold(t.title).includes(q) && !fold(t.title_en ?? '').includes(q)) return false;
		if (selectedGenres.length && !selectedGenres.some((g) => t.genres.includes(g))) return false;
		if (selectedPlatforms.length && !selectedPlatforms.some((p) => t.platforms.includes(p))) return false;
		if (selectedCountries.length && !selectedCountries.some((c) => t.countries.includes(c))) return false;
		if (selectedTags.length && !selectedTags.some((tag) => t.tags.includes(tag))) return false;
		if (selectedType && t.title_type !== selectedType) return false;
		if (yearFrom > YEAR_MIN && (t.year ?? 0) < yearFrom) return false;
		if (yearTo < YEAR_MAX && (t.year ?? 9999) > yearTo) return false;
		if (ratingMin > 0 && (t.rating ?? 0) < ratingMin) return false;
		if (selectedCrew.length && crewIdToName) {
			const names = (t.crew_ids ?? []).map((id) => crewIdToName!.get(id)).filter(Boolean);
			if (!selectedCrew.some((name) => names.includes(name))) return false;
		}
		return true;
	}

	// Filter + order within a day: group by type
	// (seriál → série → film → tv film → epizoda → ostatní), most-rated first.
	function applyFilters(list: TitleIndex[]): TitleIndex[] {
		return list.filter(passesFilters).sort((a, b) => {
			const r = typeRank(a) - typeRank(b);
			if (r !== 0) return r;
			return (b.votes_count ?? 0) - (a.votes_count ?? 0);
		});
	}

	// Layer 2 — rebuilds when filters change (cheap O(days) lookup + filter)
	let groups = $derived.by((): DayGroup[] => {
		return allDates.map((date) => {
			const { label, dayName } = formatDateLabel(date);
			return { date, label, dayName, titles: applyFilters(titlesInRange.get(date) ?? []), isToday: date === TODAY };
		});
	});

	// ── Upcoming (future) releases — opt-in section above today ────────────────
	let upcomingOpen = $state(false);
	let upcomingGroups = $derived.by((): DayGroup[] => {
		const map = new Map<string, TitleIndex[]>();
		for (const t of data.titles) {
			if (!t.vod_date || t.vod_date <= TODAY) continue;
			const arr = map.get(t.vod_date) ?? [];
			arr.push(t);
			map.set(t.vod_date, arr);
		}
		return [...map.keys()]
			.sort((a, b) => b.localeCompare(a)) // descending — latest at top, tomorrow nearest today
			.map((date) => {
				const { label, dayName } = formatDateLabel(date);
				return { date, label, dayName, titles: applyFilters(map.get(date) ?? []), isToday: false };
			})
			.filter((g) => g.titles.length > 0);
	});
	let upcomingCount = $derived(upcomingGroups.reduce((s, g) => s + g.titles.length, 0));

	// Reveal tomorrow on expand; further-out days are above it (scroll up).
	async function toggleUpcoming() {
		upcomingOpen = !upcomingOpen;
		if (!upcomingOpen) return;
		await tick();
		const soonest = upcomingGroups.at(-1)?.date; // descending → last group is nearest today
		if (soonest) {
			document.getElementById('day-' + soonest)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
		}
	}

	// ── Stats ─────────────────────────────────────────────────────────────────
	let totalTitles = $derived(groups.reduce((s, g) => s + g.titles.length, 0));
	let daysWithTitles = $derived(groups.filter((g) => g.titles.length > 0).length);

	// ── Filter dimensions + helpers (identical to Katalog) ────────────────────
	// Flat filtered set (calendar titles) drives the pill availability indicators.
	let filteredTitles = $derived(data.titles.filter((t) => t.vod_date && passesFilters(t)));

	let availableGenres = $derived(
		data.dimensions.genres.map((g) => ({ ...g, hit: filteredTitles.some((t) => t.genres.includes(g.name)) }))
	);
	let availablePlatforms = $derived(
		data.dimensions.platforms.map((p) => ({ ...p, hit: filteredTitles.some((t) => t.platforms.includes(p.name)) }))
	);
	let availableCountries = $derived(
		data.dimensions.countries.slice(0, 30).map((c) => ({ ...c, hit: filteredTitles.some((t) => t.countries.includes(c.name)) }))
	);
	let availableTags = $derived(
		data.dimensions.tags.slice(0, 50).map((tag) => ({ ...tag, hit: filteredTitles.some((t) => t.tags.includes(tag.name)) }))
	);

	let typeOptions = $derived(
		['film', 'seriál', 'tv film', 'pořad', 'krátký film'].filter((type) =>
			data.titles.some((t) => t.title_type === type)
		)
	);

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

	// ── Quick time links ──────────────────────────────────────────────────────
	function getWeekStart(weeksBack = 0): string {
		const d = new Date(TODAY + 'T12:00:00');
		const day = d.getDay() || 7; // Mon=1..Sun=7
		d.setDate(d.getDate() - (day - 1) - weeksBack * 7);
		return d.toISOString().slice(0, 10);
	}

	function getMonthStart(): string {
		const d = new Date(TODAY + 'T12:00:00');
		d.setDate(1);
		return d.toISOString().slice(0, 10);
	}

	function scrollToDate(date: string) {
		const clamped = date < minDate ? minDate : date > TODAY ? TODAY : date;
		const el = document.getElementById('day-' + clamped);
		el?.scrollIntoView({ behavior: 'smooth', block: 'start' });
	}

	// ── Modal ─────────────────────────────────────────────────────────────────
	let modalTitle = $state<TitleDetail | null>(null);
	let modalLoading = $state(false);
	let detailCache = $state<Record<string, TitleDetail> | null>(null);

	function emptyDetail(t: TitleIndex): TitleDetail {
		return {
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
	}

	async function openModal(t: TitleIndex) {
		modalLoading = true;
		modalTitle = null;
		try {
			detailCache ??= await (await fetch(`${base}/data/titles_detail.json`)).json();
			modalTitle = detailCache![`${t.id}-${t.slug}`] ?? emptyDetail(t);
		} catch {
			modalTitle = emptyDetail(t);
		} finally {
			modalLoading = false;
		}
	}

	function closeModal() {
		modalTitle = null;
		modalLoading = false;
	}

	// Resolve the serial a release belongs to (for card context + modal jump).
	let byId = $derived(new Map(data.titles.map((t) => [t.id, t])));
	function openById(id: number) {
		const e = byId.get(id);
		if (e) openModal(e);
	}
</script>

<div class="page-container">
	<!-- Header -->
	<div class="kal-header">
		<h1 class="section-title">Kalendář VOD</h1>
		<p class="kal-subtitle">
			{totalTitles} {totalTitles === 1 ? 'titul' : totalTitles < 5 ? 'tituly' : 'titulů'}
			za {daysWithTitles} {daysWithTitles === 1 ? 'den' : daysWithTitles < 5 ? 'dny' : 'dní'}
			· posledních {daysBack} dní
		</p>
	</div>

	<!-- Quick time links -->
	<div class="quick-links">
		<button class="quick-link active" onclick={() => scrollToDate(TODAY)}>Dnes</button>
		<button class="quick-link" onclick={() => scrollToDate(getWeekStart())}>Tento týden</button>
		<button class="quick-link" onclick={() => scrollToDate(getWeekStart(1))}>Minulý týden</button>
		<button class="quick-link" onclick={() => scrollToDate(getMonthStart())}>Tento měsíc</button>
	</div>

	<!-- Search + filters — identical to Katalog -->
	<div class="search-bar">
		<input
			class="search-input"
			type="search"
			placeholder="Hledat film, seriál…"
			bind:value={searchQuery}
		/>
	</div>

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

	<ActiveFilters filters={activeFilterList} onRemove={removeFilter} onClearAll={clearAll} />

	<!-- Timeline -->
	<div class="timeline">
		{#snippet dayBlock(group: DayGroup, upcoming: boolean)}
			<div
				id="day-{group.date}"
				class="day-block"
				class:is-today={group.isToday}
				class:is-upcoming={upcoming}
				class:is-empty={group.titles.length === 0}
			>
				<div class="day-header">
					{#if group.isToday}
						<span class="today-badge">DNES</span>
					{:else if upcoming}
						<span class="soon-badge">BRZY</span>
					{/if}
					<span class="day-name">{group.dayName}</span>
					<span class="day-label">{group.label}</span>
					{#if group.titles.length > 0}
						<span class="day-count">
							{group.titles.length}
							{group.titles.length === 1 ? 'titul' : group.titles.length < 5 ? 'tituly' : 'titulů'}
						</span>
					{/if}
				</div>

				{#if group.titles.length > 0}
					<div class="filmstrip scroll-row">
						{#each group.titles as title (title.id)}
							<PosterCard
								{title}
								serialTitle={title.root_title_id != null
									? byId.get(title.root_title_id)?.title
									: undefined}
								onclick={openModal}
							/>
						{/each}
					</div>
				{:else}
					<div class="day-empty">—</div>
				{/if}
			</div>
		{/snippet}

		<!-- Upcoming releases — collapsed by default, past stays primary -->
		{#if upcomingCount > 0}
			<button
				class="upcoming-toggle"
				class:open={upcomingOpen}
				onclick={toggleUpcoming}
				aria-expanded={upcomingOpen}
			>
				<span class="chev">{upcomingOpen ? '▾' : '▸'}</span>
				<span class="upcoming-name">Připravované</span>
				<span class="upcoming-count">{upcomingCount}</span>
				<span class="upcoming-hint">
					{upcomingOpen
						? 'skrýt'
						: `příštích ${upcomingGroups.length} ${upcomingGroups.length === 1 ? 'den' : upcomingGroups.length < 5 ? 'dny' : 'dní'}`}
				</span>
			</button>
			{#if upcomingOpen}
				{#each upcomingGroups as group (group.date)}
					{@render dayBlock(group, true)}
				{/each}
			{/if}
		{/if}

		{#each groups as group (group.date)}
			{@render dayBlock(group, false)}
		{/each}

		{#if daysBack < MAX_DAYS}
			<button class="load-more-btn" onclick={loadMoreDays}>
				Zobraz další dny (+{Math.min(14, MAX_DAYS - daysBack)})
			</button>
		{:else}
			<p class="load-more-end">Dosáhli jste maxima ({MAX_DAYS} dní).</p>
		{/if}
	</div>
</div>

<TitleModal title={modalTitle} loading={modalLoading} onclose={closeModal} onopentitle={openById} />

<style>
	.kal-header {
		margin-bottom: 1.25rem;
	}

	.kal-subtitle {
		color: var(--text-muted);
		font-size: 0.9rem;
		margin-top: 0.25rem;
	}

	/* Quick time links */
	.quick-links {
		display: flex;
		gap: 0.5rem;
		margin-bottom: 1.5rem;
		flex-wrap: wrap;
	}

	.quick-link {
		background: var(--navy-700);
		border: 1px solid var(--border);
		border-radius: var(--radius-sm);
		padding: 0.35rem 0.85rem;
		color: var(--text-secondary);
		font-size: 0.8rem;
		cursor: pointer;
		transition: border-color 0.15s, color 0.15s;
	}

	.quick-link:hover,
	.quick-link.active {
		border-color: var(--amber);
		color: var(--amber);
	}

	/* Search + filter bar (same as Katalog) */
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

	.filter-bar-row {
		margin-bottom: 1rem;
	}

	/* Timeline */
	.timeline {
		display: flex;
		flex-direction: column;
	}

	.day-block {
		padding: 1rem 0;
		border-top: 1px solid var(--border);
	}

	.day-block.is-today {
		border-top-color: var(--amber);
	}

	.day-block.is-empty {
		padding: 0.6rem 0;
	}

	.day-header {
		display: flex;
		align-items: baseline;
		gap: 0.6rem;
		margin-bottom: 0.75rem;
		flex-wrap: wrap;
	}

	.day-block.is-empty .day-header {
		margin-bottom: 0;
	}

	.today-badge {
		font-size: 0.62rem;
		font-weight: 800;
		letter-spacing: 0.1em;
		padding: 2px 7px;
		border-radius: 999px;
		background: var(--amber);
		color: var(--navy-900);
	}

	/* Upcoming (future) releases — cool accent to set them apart from the past */
	.upcoming-toggle {
		display: flex;
		align-items: center;
		gap: 0.6rem;
		width: 100%;
		padding: 0.7rem 0.9rem;
		margin-bottom: 0.25rem;
		background: var(--navy-800);
		border: 1px solid var(--border);
		border-radius: var(--radius);
		color: var(--text-secondary);
		font-size: 0.9rem;
		cursor: pointer;
		transition: border-color 0.15s, color 0.15s;
	}

	.upcoming-toggle:hover,
	.upcoming-toggle.open {
		border-color: rgba(110, 168, 255, 0.5);
		color: var(--text-primary);
	}

	.upcoming-toggle .chev {
		width: 1rem;
		color: #6ea8ff;
		font-size: 0.8rem;
	}

	.upcoming-name {
		font-weight: 600;
	}

	.upcoming-count {
		font-size: 0.72rem;
		font-weight: 700;
		padding: 1px 8px;
		border-radius: 999px;
		background: rgba(110, 168, 255, 0.16);
		color: #6ea8ff;
	}

	.upcoming-hint {
		margin-left: auto;
		font-size: 0.78rem;
		color: var(--text-muted);
	}

	.soon-badge {
		font-size: 0.62rem;
		font-weight: 800;
		letter-spacing: 0.1em;
		padding: 2px 7px;
		border-radius: 999px;
		background: rgba(110, 168, 255, 0.16);
		color: #6ea8ff;
	}

	.day-block.is-upcoming {
		border-top-color: rgba(110, 168, 255, 0.35);
	}

	.day-name {
		font-weight: 600;
		font-size: 0.95rem;
		color: var(--text-primary);
	}

	.day-block.is-empty .day-name {
		color: var(--text-muted);
		font-weight: 400;
	}

	.day-label {
		font-size: 0.82rem;
		color: var(--text-muted);
	}

	.day-count {
		font-size: 0.75rem;
		color: var(--text-muted);
		margin-left: auto;
	}

	.filmstrip :global(.poster-card) {
		flex: 0 0 150px;
	}

	.day-empty {
		font-size: 0.8rem;
		color: var(--navy-600);
		padding-left: 0.25rem;
	}

	/* Load more */
	.load-more-btn {
		align-self: center;
		margin: 1.75rem auto 0.5rem;
		padding: 0.6rem 1.5rem;
		background: var(--navy-700);
		border: 1px solid var(--border);
		border-radius: var(--radius);
		color: var(--text-primary);
		font-size: 0.9rem;
		cursor: pointer;
		transition: border-color 0.15s, color 0.15s;
	}

	.load-more-btn:hover {
		border-color: var(--amber);
		color: var(--amber);
	}

	.load-more-end {
		align-self: center;
		margin: 1.75rem auto 0.5rem;
		color: var(--text-muted);
		font-size: 0.85rem;
	}

	@media (max-width: 640px) {
		.filmstrip :global(.poster-card) {
			flex: 0 0 120px;
		}
	}
</style>

<script lang="ts">
	import { untrack } from 'svelte';
	import type { PageData } from './$types';
	import type { TitleIndex, TitleDetail } from '$lib/types';
	import PosterCard from '$lib/components/PosterCard.svelte';
	import TitleModal from '$lib/components/TitleModal.svelte';
	import { base } from '$app/paths';

	let { data }: { data: PageData } = $props();

	// ── Date constants ────────────────────────────────────────────────────────
	const TODAY = new Date().toISOString().slice(0, 10);
	const MAX_DAYS = 365;
	const DEFAULT_DAYS = 28;

	const CS_MONTHS = ['ledna','února','března','dubna','května','června','července','srpna','září','října','listopadu','prosince'];
	const CS_DAYS = ['Neděle','Pondělí','Úterý','Středa','Čtvrtek','Pátek','Sobota'];

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

	// ── Reactive state ────────────────────────────────────────────────────────
	// untrack: seed once from URL params, then manage locally.
	// Without untrack, SvelteKit navigation updating `data` would re-initialize state.
	let daysBack = $state<number>(untrack(() => data.initialDays));
	let selectedPlatform = $state(untrack(() => data.initialPlatform));
	let selectedType = $state(untrack(() => data.initialType));
	let selectedGenre = $state(untrack(() => data.initialGenre));

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
		if (selectedPlatform) params.set('platform', selectedPlatform);
		if (selectedType)     params.set('type',     selectedType);
		if (selectedGenre)    params.set('genre',    selectedGenre);
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

	// Layer 2 — rebuilds when filters change (cheap O(days) lookup + filter)
	let groups = $derived.by((): DayGroup[] => {
		return allDates.map((date) => {
			let titles = [...(titlesInRange.get(date) ?? [])];
			if (selectedPlatform) titles = titles.filter((t) => t.platforms.includes(selectedPlatform));
			if (selectedType)     titles = titles.filter((t) => t.title_type === selectedType);
			if (selectedGenre)    titles = titles.filter((t) => t.genres.includes(selectedGenre));
			titles.sort((a, b) => (b.rating ?? 0) - (a.rating ?? 0));
			const { label, dayName } = formatDateLabel(date);
			return { date, label, dayName, titles, isToday: date === TODAY };
		});
	});

	// ── Stats ─────────────────────────────────────────────────────────────────
	let totalTitles = $derived(groups.reduce((s, g) => s + g.titles.length, 0));
	let daysWithTitles = $derived(groups.filter((g) => g.titles.length > 0).length);

	// ── Dimension options ─────────────────────────────────────────────────────
	let topPlatforms = $derived(data.dimensions.platforms.slice(0, 10));
	let topGenres = $derived(data.dimensions.genres.slice(0, 14));

	// Single-pass scan with early exit — stops as soon as all 4 types are found
	let typeOptions = $derived.by(() => {
		const seen = new Set<string>();
		const candidates = new Set(['film', 'seriál', 'tv film', 'pořad']);
		for (const t of data.titles) {
			if (t.title_type && candidates.has(t.title_type) && t.vod_date != null && t.vod_date >= minDate) {
				seen.add(t.title_type);
				if (seen.size === candidates.size) break;
			}
		}
		return ['film', 'seriál', 'tv film', 'pořad'].filter((t) => seen.has(t));
	});

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

	<!-- Filters -->
	<div class="filter-bar">
		<!-- Platform -->
		<div class="filter-section">
			<span class="filter-label">Platforma</span>
			<div class="pill-row">
				<button
					class="pill"
					class:active={selectedPlatform === ''}
					onclick={() => (selectedPlatform = '')}
				>Vše</button>
				{#each topPlatforms as p}
					<button
						class="pill"
						class:active={selectedPlatform === p.name}
						onclick={() => (selectedPlatform = selectedPlatform === p.name ? '' : p.name)}
					>{p.name}</button>
				{/each}
			</div>
		</div>

		<!-- Type -->
		{#if typeOptions.length > 0}
			<div class="filter-section">
				<span class="filter-label">Typ</span>
				<div class="pill-row">
					<button
						class="pill"
						class:active={selectedType === ''}
						onclick={() => (selectedType = '')}
					>Vše</button>
					{#each typeOptions as type}
						<button
							class="pill"
							class:active={selectedType === type}
							onclick={() => (selectedType = selectedType === type ? '' : type)}
						>{type}</button>
					{/each}
				</div>
			</div>
		{/if}

		<!-- Genre -->
		<div class="filter-section">
			<span class="filter-label">Žánr</span>
			<div class="pill-row">
				<button
					class="pill"
					class:active={selectedGenre === ''}
					onclick={() => (selectedGenre = '')}
				>Vše</button>
				{#each topGenres as g}
					<button
						class="pill"
						class:active={selectedGenre === g.name}
						onclick={() => (selectedGenre = selectedGenre === g.name ? '' : g.name)}
					>{g.name}</button>
				{/each}
			</div>
		</div>
	</div>

	<!-- Timeline -->
	<div class="timeline">
		{#each groups as group (group.date)}
			<div
				id="day-{group.date}"
				class="day-block"
				class:is-today={group.isToday}
				class:is-empty={group.titles.length === 0}
			>
				<div class="day-header">
					{#if group.isToday}
						<span class="today-badge">DNES</span>
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
							<PosterCard {title} onclick={openModal} />
						{/each}
					</div>
				{:else}
					<div class="day-empty">—</div>
				{/if}
			</div>
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

<TitleModal title={modalTitle} loading={modalLoading} onclose={closeModal} />

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

	/* Filter bar */
	.filter-bar {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
		margin-bottom: 2rem;
		padding: 1rem 1.25rem;
		background: var(--navy-800);
		border: 1px solid var(--border);
		border-radius: var(--radius);
	}

	.filter-section {
		display: flex;
		align-items: flex-start;
		gap: 0.75rem;
	}

	.filter-label {
		font-size: 0.68rem;
		font-weight: 700;
		letter-spacing: 0.08em;
		text-transform: uppercase;
		color: var(--text-muted);
		white-space: nowrap;
		padding-top: 5px;
		min-width: 60px;
	}

	.pill-row {
		display: flex;
		flex-wrap: wrap;
		gap: 0.35rem;
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

		.filter-section {
			flex-direction: column;
			gap: 0.4rem;
		}

		.filter-label {
			padding-top: 0;
		}
	}
</style>

<script lang="ts">
	import type { PageData } from './$types';
	import type { TitleIndex } from '$lib/types';
	import PosterCard from '$lib/components/PosterCard.svelte';

	let { data }: { data: PageData } = $props();

	// ── Build date-grouped structure ──────────────────────────────────────────
	interface DayGroup {
		date: string;       // ISO "YYYY-MM-DD"
		label: string;      // "1. května 2026"
		dayName: string;    // "Pondělí"
		titles: TitleIndex[];
		isToday: boolean;
		isFuture: boolean;
	}

	const TODAY = new Date().toISOString().slice(0, 10);

	const CS_MONTHS = ['ledna','února','března','dubna','května','června','července','srpna','září','října','listopadu','prosince'];
	const CS_DAYS = ['Neděle','Pondělí','Úterý','Středa','Čtvrtek','Pátek','Sobota'];

	function formatDateLabel(iso: string): { label: string; dayName: string } {
		const d = new Date(iso + 'T12:00:00');
		const day = d.getDate();
		const month = CS_MONTHS[d.getMonth()];
		const year = d.getFullYear();
		const dayName = CS_DAYS[d.getDay()];
		return { label: `${day}. ${month} ${year}`, dayName };
	}

	let groups = $derived.by((): DayGroup[] => {
		const map = new Map<string, TitleIndex[]>();
		for (const t of data.titles) {
			if (!t.vod_date) continue;
			const arr = map.get(t.vod_date) ?? [];
			arr.push(t);
			map.set(t.vod_date, arr);
		}

		return [...map.entries()]
			.sort(([a], [b]) => b.localeCompare(a)) // newest first
			.map(([date, titles]) => {
				const { label, dayName } = formatDateLabel(date);
				// Sort by rating desc within each day
				titles.sort((a, b) => (b.rating ?? 0) - (a.rating ?? 0));
				return {
					date,
					label,
					dayName,
					titles,
					isToday: date === TODAY,
					isFuture: date > TODAY
				};
			});
	});

	// ── Platform filter ───────────────────────────────────────────────────────
	let selectedPlatform = $state('');

	let filteredGroups = $derived(
		selectedPlatform
			? groups
				.map((g) => ({
					...g,
					titles: g.titles.filter((t) => t.platforms.includes(selectedPlatform))
				}))
				.filter((g) => g.titles.length > 0)
			: groups
	);

	let topPlatforms = $derived(
		data.dimensions.platforms.slice(0, 10)
	);

	// ── Stats ─────────────────────────────────────────────────────────────────
	let totalDays = $derived(filteredGroups.length);
	let totalTitles = $derived(filteredGroups.reduce((s, g) => s + g.titles.length, 0));
</script>

<div class="page-container">
	<div class="kal-header">
		<h1 class="section-title">Kalendář VOD</h1>
		<p class="kal-subtitle">{totalTitles} titulů za {totalDays} dní</p>
	</div>

	<!-- Platform quick filter -->
	<div class="platform-strip">
		<button
			class="pill"
			class:active={selectedPlatform === ''}
			onclick={() => (selectedPlatform = '')}
		>
			Vše
		</button>
		{#each topPlatforms as p}
			<button
				class="pill"
				class:active={selectedPlatform === p.name}
				onclick={() => (selectedPlatform = selectedPlatform === p.name ? '' : p.name)}
			>
				{p.name}
			</button>
		{/each}
	</div>

	<!-- Timeline -->
	<div class="timeline">
		{#each filteredGroups as group (group.date)}
			<div
				class="day-block"
				class:is-today={group.isToday}
				class:is-future={group.isFuture}
			>
				<!-- Day header -->
				<div class="day-header">
					{#if group.isToday}
						<span class="today-badge">DNES</span>
					{/if}
					<span class="day-name">{group.dayName}</span>
					<span class="day-label">{group.label}</span>
					<span class="day-count">{group.titles.length} {group.titles.length === 1 ? 'titul' : group.titles.length < 5 ? 'tituly' : 'titulů'}</span>
				</div>

				<!-- Horizontal filmstrip -->
				<div class="filmstrip scroll-row">
					{#each group.titles as title (title.id)}
						<PosterCard {title} />
					{/each}
				</div>
			</div>
		{/each}

		{#if filteredGroups.length === 0}
			<div class="empty-state">
				<p>Žádné tituly pro vybranou platformu.</p>
			</div>
		{/if}
	</div>
</div>

<style>
	.kal-header {
		margin-bottom: 1.25rem;
	}

	.kal-subtitle {
		color: var(--text-muted);
		font-size: 0.9rem;
		margin-top: 0.25rem;
	}

	.platform-strip {
		display: flex;
		flex-wrap: wrap;
		gap: 0.4rem;
		margin-bottom: 2rem;
	}

	.timeline {
		display: flex;
		flex-direction: column;
		gap: 0;
	}

	.day-block {
		padding: 1.25rem 0;
		border-top: 1px solid var(--border);
	}

	.day-block.is-today {
		border-top-color: var(--amber);
	}

	.day-block.is-future .day-name,
	.day-block.is-future .day-label {
		color: var(--text-secondary);
	}

	.day-header {
		display: flex;
		align-items: baseline;
		gap: 0.75rem;
		margin-bottom: 0.9rem;
		flex-wrap: wrap;
	}

	.today-badge {
		font-size: 0.65rem;
		font-weight: 800;
		letter-spacing: 0.1em;
		padding: 2px 7px;
		border-radius: 999px;
		background: var(--amber);
		color: var(--navy-900);
	}

	.day-name {
		font-weight: 600;
		font-size: 1rem;
		color: var(--text-primary);
	}

	.day-label {
		font-size: 0.85rem;
		color: var(--text-muted);
	}

	.day-count {
		font-size: 0.78rem;
		color: var(--text-muted);
		margin-left: auto;
	}

	.filmstrip {
		/* inherits .scroll-row from global */
	}

	.filmstrip :global(.poster-card) {
		flex: 0 0 150px;
	}

	@media (max-width: 640px) {
		.filmstrip :global(.poster-card) {
			flex: 0 0 120px;
		}
	}

	.empty-state {
		padding: 3rem 0;
		color: var(--text-muted);
		text-align: center;
	}
</style>

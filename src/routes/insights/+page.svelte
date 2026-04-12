<script lang="ts">
	import type { PageData } from './$types';
	import type { TitleIndex } from '$lib/types';
	import { base } from '$app/paths';

	let { data }: { data: PageData } = $props();

	// ── Helper ────────────────────────────────────────────────────────────────
	function counter<K extends string>(items: K[]): { name: K; count: number }[] {
		const m = new Map<K, number>();
		for (const v of items) m.set(v, (m.get(v) ?? 0) + 1);
		return [...m.entries()]
			.map(([name, count]) => ({ name, count }))
			.sort((a, b) => b.count - a.count);
	}

	// ── Stats ─────────────────────────────────────────────────────────────────
	const titles = data.titles;
	const withRating = titles.filter((t) => t.rating !== null);

	let totalTitles = $derived(titles.length);
	let totalFilms = $derived(titles.filter((t) => t.title_type === 'film').length);
	let totalSerials = $derived(titles.filter((t) => t.title_type === 'seriál').length);
	let avgRating = $derived(
		withRating.length
			? Math.round(withRating.reduce((s, t) => s + t.rating!, 0) / withRating.length)
			: null
	);
	let platformCount = $derived(data.dimensions.platforms.length);
	let genreCount = $derived(data.dimensions.genres.length);

	// ── Titles per platform ───────────────────────────────────────────────────
	let perPlatform = $derived(
		data.dimensions.platforms.slice(0, 12).map((p) => ({
			name: p.name,
			count: titles.filter((t) => t.platforms.includes(p.name)).length
		}))
	);
	let maxPlatform = $derived(Math.max(...perPlatform.map((p) => p.count), 1));

	// ── Titles per year ───────────────────────────────────────────────────────
	let perYear = $derived.by(() => {
		const m = new Map<number, number>();
		for (const t of titles) {
			if (t.year && t.year >= 1950 && t.year <= new Date().getFullYear()) {
				m.set(t.year, (m.get(t.year) ?? 0) + 1);
			}
		}
		return [...m.entries()]
			.sort(([a], [b]) => a - b)
			.map(([year, count]) => ({ year, count }));
	});
	let maxYear = $derived(Math.max(...perYear.map((y) => y.count), 1));

	// ── Rating distribution ───────────────────────────────────────────────────
	let ratingBuckets = $derived.by(() => {
		const buckets: { label: string; count: number }[] = [
			{ label: '0–19', count: 0 },
			{ label: '20–39', count: 0 },
			{ label: '40–59', count: 0 },
			{ label: '60–69', count: 0 },
			{ label: '70–79', count: 0 },
			{ label: '80–89', count: 0 },
			{ label: '90+', count: 0 },
		];
		for (const t of withRating) {
			const r = t.rating!;
			if (r < 20) buckets[0].count++;
			else if (r < 40) buckets[1].count++;
			else if (r < 60) buckets[2].count++;
			else if (r < 70) buckets[3].count++;
			else if (r < 80) buckets[4].count++;
			else if (r < 90) buckets[5].count++;
			else buckets[6].count++;
		}
		return buckets;
	});
	let maxBucket = $derived(Math.max(...ratingBuckets.map((b) => b.count), 1));

	// ── Top genres ────────────────────────────────────────────────────────────
	let topGenres = $derived(data.dimensions.genres.slice(0, 15));

	// ── Hidden gems ── high rating, low votes ────────────────────────────────
	let hiddenGems = $derived(
		titles
			.filter((t) => t.rating !== null && t.rating >= 75 && t.votes_count !== null && t.votes_count < 500 && t.votes_count > 10)
			.sort((a, b) => (b.rating ?? 0) - (a.rating ?? 0))
			.slice(0, 10)
	);

	// ── Monthly VOD additions ────────────────────────────────────────────────
	let perMonth = $derived.by(() => {
		const m = new Map<string, number>();
		for (const t of titles) {
			if (!t.vod_date) continue;
			const month = t.vod_date.slice(0, 7); // "2026-04"
			m.set(month, (m.get(month) ?? 0) + 1);
		}
		return [...m.entries()]
			.sort(([a], [b]) => a.localeCompare(b))
			.slice(-18) // last 18 months
			.map(([month, count]) => {
				const [y, mo] = month.split('-');
				return { month, label: `${mo}/${y.slice(2)}`, count };
			});
	});
	let maxMonth = $derived(Math.max(...perMonth.map((m) => m.count), 1));

	// ── Bar chart helpers ─────────────────────────────────────────────────────
	const BAR_HEIGHT = 28;
	const BAR_GAP = 6;
	const LABEL_W = 110;
	const CHART_W = 420;
	const VALUE_PAD = 6;

	function barWidth(count: number, max: number) {
		return Math.max(2, Math.round((count / max) * CHART_W));
	}

	function barColor(count: number, max: number) {
		const ratio = count / max;
		if (ratio > 0.7) return 'var(--amber)';
		if (ratio > 0.4) return '#f5c76a';
		return 'var(--navy-500)';
	}
</script>

<div class="page-container">
	<h1 class="section-title">Insights</h1>

	<!-- Stat cards -->
	<div class="stat-grid">
		<div class="stat-card">
			<span class="stat-num">{totalTitles.toLocaleString('cs')}</span>
			<span class="stat-label">titulů celkem</span>
		</div>
		<div class="stat-card">
			<span class="stat-num">{totalFilms.toLocaleString('cs')}</span>
			<span class="stat-label">filmů</span>
		</div>
		<div class="stat-card">
			<span class="stat-num">{totalSerials.toLocaleString('cs')}</span>
			<span class="stat-label">seriálů</span>
		</div>
		{#if avgRating !== null}
			<div class="stat-card">
				<span class="stat-num" style="color: var(--amber)">{avgRating} %</span>
				<span class="stat-label">průměrné hodnocení</span>
			</div>
		{/if}
		<div class="stat-card">
			<span class="stat-num">{platformCount}</span>
			<span class="stat-label">VOD platforem</span>
		</div>
		<div class="stat-card">
			<span class="stat-num">{genreCount}</span>
			<span class="stat-label">žánrů</span>
		</div>
	</div>

	<div class="charts-grid">
		<!-- Titles per platform -->
		<section class="chart-section">
			<h2 class="chart-title">Tituly dle platformy</h2>
			<div class="h-bar-chart">
				{#each perPlatform as p, i}
					<div class="h-bar-row" style="top: {i * (BAR_HEIGHT + BAR_GAP)}px">
						<span class="h-bar-label">{p.name}</span>
						<div class="h-bar-track">
							<div
								class="h-bar-fill"
								style="width: {barWidth(p.count, maxPlatform)}px; background: {barColor(p.count, maxPlatform)}"
							></div>
							<span class="h-bar-value">{p.count}</span>
						</div>
					</div>
				{/each}
			</div>
		</section>

		<!-- Rating distribution -->
		<section class="chart-section">
			<h2 class="chart-title">Rozložení hodnocení</h2>
			<div class="h-bar-chart">
				{#each ratingBuckets as b, i}
					<div class="h-bar-row" style="top: {i * (BAR_HEIGHT + BAR_GAP)}px">
						<span class="h-bar-label">{b.label} %</span>
						<div class="h-bar-track">
							<div
								class="h-bar-fill"
								style="width: {barWidth(b.count, maxBucket)}px; background: {barColor(b.count, maxBucket)}"
							></div>
							<span class="h-bar-value">{b.count}</span>
						</div>
					</div>
				{/each}
			</div>
		</section>

		<!-- Top genres -->
		<section class="chart-section">
			<h2 class="chart-title">Top žánry</h2>
			<div class="h-bar-chart">
				{#each topGenres as g, i}
					<div class="h-bar-row" style="top: {i * (BAR_HEIGHT + BAR_GAP)}px">
						<a class="h-bar-label genre-link" href="{base}/katalog?genre={g.name}">{g.name}</a>
						<div class="h-bar-track">
							<div
								class="h-bar-fill"
								style="width: {barWidth(g.count, topGenres[0]?.count ?? 1)}px; background: {barColor(g.count, topGenres[0]?.count ?? 1)}"
							></div>
							<span class="h-bar-value">{g.count}</span>
						</div>
					</div>
				{/each}
			</div>
		</section>

		<!-- Monthly additions -->
		{#if perMonth.length > 2}
			<section class="chart-section chart-section--wide">
				<h2 class="chart-title">Přírůstky po měsících</h2>
				<div class="month-bars">
					{#each perMonth as m}
						<div class="month-col">
							<span class="month-count">{m.count}</span>
							<div
								class="month-bar"
								style="height: {Math.max(4, Math.round((m.count / maxMonth) * 120))}px; background: {barColor(m.count, maxMonth)}"
							></div>
							<span class="month-label">{m.label}</span>
						</div>
					{/each}
				</div>
			</section>
		{/if}
	</div>

	<!-- Hidden gems -->
	{#if hiddenGems.length > 0}
		<section class="gems-section">
			<h2 class="chart-title">Skryté klenoty <span class="gems-subtitle">— vysoké hodnocení, málo diváků</span></h2>
			<div class="gems-grid">
				{#each hiddenGems as t (t.id)}
					<a class="gem-card" href="{base}/titul/{t.id}/{t.slug}">
						{#if t.poster}
							<img src={t.poster} alt={t.title} />
						{:else}
							<div class="gem-placeholder">{t.title}</div>
						{/if}
						<div class="gem-info">
							<p class="gem-title">{t.title}</p>
							<div class="gem-meta">
								<span class="gem-rating">{t.rating} %</span>
								{#if t.year}<span class="gem-year">{t.year}</span>{/if}
							</div>
							{#if t.votes_count}
								<span class="gem-votes">{t.votes_count} hodnocení</span>
							{/if}
						</div>
					</a>
				{/each}
			</div>
		</section>
	{/if}

	<!-- Year histogram (SVG) -->
	{#if perYear.length > 5}
		<section class="chart-section chart-section--wide" style="margin-top: 2rem;">
			<h2 class="chart-title">Tituly dle roku výroby</h2>
			<div class="year-chart-wrap">
				<svg
					class="year-svg"
					viewBox="0 0 {perYear.length * 14} 100"
					preserveAspectRatio="none"
					aria-hidden="true"
				>
					{#each perYear as y, i}
						{@const h = Math.max(2, Math.round((y.count / maxYear) * 90))}
						<rect
							x={i * 14 + 1}
							y={100 - h}
							width={12}
							height={h}
							fill={barColor(y.count, maxYear)}
							rx="1"
						>
							<title>{y.year}: {y.count}</title>
						</rect>
					{/each}
				</svg>
				<div class="year-axis">
					<span>{perYear[0]?.year}</span>
					<span>{perYear[Math.floor(perYear.length / 2)]?.year}</span>
					<span>{perYear[perYear.length - 1]?.year}</span>
				</div>
			</div>
		</section>
	{/if}
</div>

<style>
	/* Stat cards */
	.stat-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
		gap: 1rem;
		margin-bottom: 2.5rem;
	}

	.stat-card {
		background: var(--navy-700);
		border: 1px solid var(--border);
		border-radius: var(--radius);
		padding: 1.25rem 1.5rem;
		display: flex;
		flex-direction: column;
		gap: 0.3rem;
	}

	.stat-num {
		font-family: 'Georgia', serif;
		font-size: 2rem;
		font-weight: 700;
		color: var(--text-primary);
		line-height: 1;
	}

	.stat-label {
		font-size: 0.78rem;
		color: var(--text-muted);
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}

	/* Charts grid */
	.charts-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
		gap: 2rem;
		margin-bottom: 2.5rem;
	}

	.chart-section {
		background: var(--navy-800);
		border: 1px solid var(--border);
		border-radius: var(--radius);
		padding: 1.5rem;
	}

	.chart-section--wide {
		grid-column: 1 / -1;
	}

	.chart-title {
		font-size: 0.85rem;
		font-weight: 700;
		letter-spacing: 0.06em;
		text-transform: uppercase;
		color: var(--text-muted);
		margin-bottom: 1.25rem;
	}

	/* Horizontal bar chart */
	.h-bar-chart {
		position: relative;
	}

	.h-bar-row {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		margin-bottom: 6px;
	}

	.h-bar-label {
		width: 95px;
		min-width: 95px;
		font-size: 0.78rem;
		color: var(--text-secondary);
		text-align: right;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}

	.genre-link {
		color: var(--text-secondary);
		text-decoration: none;
	}

	.genre-link:hover {
		color: var(--amber);
	}

	.h-bar-track {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		flex: 1;
	}

	.h-bar-fill {
		height: 20px;
		border-radius: 2px;
		min-width: 2px;
		transition: width 0.3s ease;
	}

	.h-bar-value {
		font-size: 0.75rem;
		color: var(--text-muted);
		white-space: nowrap;
	}

	/* Month bars (vertical) */
	.month-bars {
		display: flex;
		align-items: flex-end;
		gap: 0.25rem;
		height: 160px;
		padding-top: 1.5rem;
	}

	.month-col {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 4px;
		flex: 1;
	}

	.month-count {
		font-size: 0.6rem;
		color: var(--text-muted);
	}

	.month-bar {
		width: 100%;
		border-radius: 2px 2px 0 0;
	}

	.month-label {
		font-size: 0.6rem;
		color: var(--text-muted);
		writing-mode: vertical-rl;
		transform: rotate(180deg);
		white-space: nowrap;
	}

	/* Year SVG histogram */
	.year-chart-wrap {
		overflow-x: auto;
	}

	.year-svg {
		width: 100%;
		height: 100px;
		display: block;
	}

	.year-axis {
		display: flex;
		justify-content: space-between;
		font-size: 0.72rem;
		color: var(--text-muted);
		margin-top: 4px;
	}

	/* Hidden gems */
	.gems-section {
		margin-top: 2rem;
	}

	.gems-subtitle {
		font-size: 0.8rem;
		font-weight: 400;
		color: var(--text-muted);
		text-transform: none;
		letter-spacing: 0;
	}

	.gems-grid {
		display: flex;
		gap: 1rem;
		overflow-x: auto;
		padding-bottom: 0.75rem;
		scrollbar-width: thin;
		scrollbar-color: var(--navy-500) transparent;
		margin-top: 1rem;
	}

	.gem-card {
		display: flex;
		flex-direction: column;
		flex: 0 0 130px;
		border-radius: var(--radius);
		overflow: hidden;
		background: var(--navy-700);
		text-decoration: none;
		transition: transform 0.2s;
	}

	.gem-card:hover {
		transform: translateY(-3px);
	}

	.gem-card img {
		width: 100%;
		aspect-ratio: 2/3;
		object-fit: cover;
	}

	.gem-placeholder {
		width: 100%;
		aspect-ratio: 2/3;
		background: var(--navy-600);
		display: flex;
		align-items: center;
		justify-content: center;
		font-size: 0.7rem;
		color: var(--text-muted);
		padding: 0.5rem;
		text-align: center;
	}

	.gem-info {
		padding: 0.5rem 0.6rem;
	}

	.gem-title {
		font-size: 0.78rem;
		font-weight: 600;
		color: var(--text-primary);
		line-height: 1.3;
		display: -webkit-box;
		-webkit-line-clamp: 2;
		-webkit-box-orient: vertical;
		overflow: hidden;
	}

	.gem-meta {
		display: flex;
		gap: 0.4rem;
		align-items: center;
		margin-top: 0.25rem;
	}

	.gem-rating {
		font-size: 0.75rem;
		font-weight: 700;
		color: #4caf50;
	}

	.gem-year {
		font-size: 0.72rem;
		color: var(--text-muted);
	}

	.gem-votes {
		font-size: 0.68rem;
		color: var(--text-muted);
	}
</style>

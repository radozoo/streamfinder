<script lang="ts">
	import type { PageData } from './$types';
	import { base } from '$app/paths';
	import PosterCard from '$lib/components/PosterCard.svelte';
	import type { TitleIndex } from '$lib/types';

	let { data }: { data: PageData } = $props();

	function formatDate(iso: string) {
		const d = new Date(iso);
		return d.toLocaleDateString('cs-CZ', { day: 'numeric', month: 'long' });
	}

	function ratingClass(r: number | null) {
		if (!r) return '';
		if (r >= 75) return 'rating-great';
		if (r >= 60) return 'rating-good';
		return 'rating-avg';
	}
</script>

<!-- Hero -->
<section class="hero">
	{#if data.featured}
		{@const f = data.featured}
		<div class="hero-featured">
			{#if f.poster}
				<div class="hero-poster">
					<img src={f.poster} alt={f.title} loading="eager" />
				</div>
			{/if}
			<div class="hero-info">
				<div class="hero-badges">
					{#each f.platforms.slice(0, 2) as p}
						<span class="vod-badge">{p}</span>
					{/each}
					{#if f.vod_date}
						<span class="hero-date">od {formatDate(f.vod_date)}</span>
					{/if}
				</div>
				<h1 class="hero-title">{f.title}</h1>
				{#if f.title_en && f.title_en !== f.title}
					<p class="hero-title-en">{f.title_en} ({f.year})</p>
				{:else if f.year}
					<p class="hero-title-en">{f.year}</p>
				{/if}
				<div class="hero-meta">
					{#if f.rating !== null}
						<span class="hero-rating {ratingClass(f.rating)}">{f.rating} %</span>
					{/if}
					{#if f.votes_count}
						<span class="hero-votes">{f.votes_count.toLocaleString('cs-CZ')} hodnocení</span>
					{/if}
					{#if f.runtime_min}
						<span class="hero-runtime">{Math.floor(f.runtime_min / 60)}h {f.runtime_min % 60}min</span>
					{/if}
				</div>
				<div class="hero-genres">
					{#each f.genres.slice(0, 4) as g}
						<a href="{base}/katalog?genre={encodeURIComponent(g)}" class="pill">{g}</a>
					{/each}
				</div>
				<a href="{base}/titul/{f.id}/{f.slug}" class="hero-cta">Detail →</a>
			</div>
		</div>

		<div class="hero-recent">
			<div class="recent-section">
				<h3 class="recent-heading">Nedávno přibylo</h3>
				<ul class="recent-dates">
					{#each data.recentDates as [date, count]}
						<li>
							<span class="recent-date">{formatDate(date)}</span>
							<span class="recent-count">{count} {count === 1 ? 'titul' : count < 5 ? 'tituly' : 'titulů'}</span>
						</li>
					{/each}
				</ul>
				<a href="{base}/kalendar" class="recent-cta">Celý kalendář →</a>
			</div>
		</div>
	{:else}
		<div class="hero-empty">
			<p>Žádný doporučený titul momentálně není k dispozici.</p>
		</div>
	{/if}
</section>

<!-- New this week -->
{#if data.newThisWeek.length > 0}
<section class="home-section page-container">
	<h2 class="section-title">Nové na VOD tento týden</h2>
	<div class="scroll-row">
		{#each data.newThisWeek as title}
			<PosterCard {title} />
		{/each}
	</div>
</section>
{/if}

<!-- Best this month -->
{#if data.bestThisMonth.length > 0}
<section class="home-section page-container">
	<h2 class="section-title">Nejlépe hodnocené tento měsíc</h2>
	<div class="scroll-row">
		{#each data.bestThisMonth as title}
			<PosterCard {title} />
		{/each}
	</div>
</section>
{/if}

<!-- Browse by genre -->
<section class="home-section page-container">
	<h2 class="section-title">Procházej podle žánru</h2>
	<div class="genre-tiles">
		{#each data.dimensions.genres.slice(0, 16) as g}
			<a href="{base}/katalog?genre={encodeURIComponent(g.name)}" class="genre-tile">
				<span class="genre-name">{g.name}</span>
				<span class="genre-count">{g.count}</span>
			</a>
		{/each}
	</div>
</section>

<!-- Stats teaser -->
<section class="home-section home-stats page-container">
	<div class="stat">
		<span class="stat-num">{data.stats.total.toLocaleString('cs-CZ')}</span>
		<span class="stat-label">titulů</span>
	</div>
	<div class="stat">
		<span class="stat-num">{data.stats.platforms}</span>
		<span class="stat-label">platforem</span>
	</div>
	<div class="stat">
		<span class="stat-num">{data.stats.genres}</span>
		<span class="stat-label">žánrů</span>
	</div>
	<div class="stat">
		<span class="stat-num">{data.stats.avgRating} %</span>
		<span class="stat-label">průměrné hodnocení</span>
	</div>
	<a href="{base}/insights" class="stat-cta">Celé Insights →</a>
</section>

<style>
	/* Hero */
	.hero {
		display: grid;
		grid-template-columns: 1fr auto;
		min-height: 480px;
		background: linear-gradient(135deg, var(--navy-800), var(--navy-900));
		border-bottom: 1px solid var(--border);
	}

	.hero-featured {
		display: flex;
		align-items: center;
		gap: 2.5rem;
		padding: 3rem 2.5rem;
	}

	.hero-poster {
		flex: 0 0 200px;
	}

	.hero-poster img {
		width: 100%;
		border-radius: var(--radius);
		box-shadow: 0 24px 60px rgba(0, 0, 0, 0.7);
		aspect-ratio: 2/3;
		object-fit: cover;
	}

	.hero-info {
		flex: 1;
		min-width: 0;
	}

	.hero-badges {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		margin-bottom: 0.75rem;
		flex-wrap: wrap;
	}

	.hero-date {
		font-size: 0.75rem;
		color: var(--text-muted);
	}

	.hero-title {
		font-family: 'Georgia', serif;
		font-size: 2.2rem;
		font-weight: 700;
		line-height: 1.2;
		letter-spacing: -0.03em;
		color: var(--text-primary);
		margin-bottom: 0.35rem;
	}

	.hero-title-en {
		font-size: 0.95rem;
		color: var(--text-secondary);
		margin-bottom: 1rem;
	}

	.hero-meta {
		display: flex;
		align-items: center;
		gap: 1rem;
		margin-bottom: 1rem;
		flex-wrap: wrap;
	}

	.hero-rating {
		font-size: 1.5rem;
		font-weight: 800;
		color: var(--amber);
	}

	.hero-votes, .hero-runtime {
		font-size: 0.85rem;
		color: var(--text-secondary);
	}

	.hero-genres {
		display: flex;
		gap: 0.5rem;
		flex-wrap: wrap;
		margin-bottom: 1.5rem;
	}

	.hero-cta {
		display: inline-block;
		padding: 0.6rem 1.5rem;
		background: var(--amber);
		color: var(--navy-900);
		font-weight: 700;
		font-size: 0.9rem;
		border-radius: 6px;
		transition: background 0.2s;
	}

	.hero-cta:hover {
		background: var(--amber-dim);
	}

	/* Recent arrivals sidebar */
	.hero-recent {
		padding: 3rem 2.5rem 3rem 0;
		width: 280px;
		display: flex;
		align-items: center;
	}

	.recent-section {
		width: 100%;
	}

	.recent-heading {
		font-size: 0.75rem;
		font-weight: 700;
		text-transform: uppercase;
		letter-spacing: 0.08em;
		color: var(--text-muted);
		margin-bottom: 1rem;
	}

	.recent-dates {
		list-style: none;
		display: flex;
		flex-direction: column;
		gap: 0.6rem;
	}

	.recent-dates li {
		display: flex;
		justify-content: space-between;
		align-items: baseline;
		gap: 1rem;
	}

	.recent-date {
		font-size: 0.85rem;
		color: var(--text-primary);
	}

	.recent-count {
		font-size: 0.75rem;
		color: var(--text-muted);
	}

	.recent-cta {
		display: block;
		margin-top: 1.25rem;
		font-size: 0.8rem;
		color: var(--amber);
	}

	.hero-empty {
		padding: 3rem;
		color: var(--text-muted);
	}

	/* Genre tiles */
	.genre-tiles {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(130px, 1fr));
		gap: 0.75rem;
	}

	.genre-tile {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 0.3rem;
		padding: 1rem 0.75rem;
		background: var(--navy-700);
		border: 1px solid var(--border);
		border-radius: var(--radius);
		cursor: pointer;
		transition: all 0.2s;
		text-align: center;
	}

	.genre-tile:hover {
		background: var(--navy-600);
		border-color: var(--amber);
	}

	.genre-name {
		font-size: 0.9rem;
		font-weight: 600;
		color: var(--text-primary);
	}

	.genre-count {
		font-size: 0.72rem;
		color: var(--text-muted);
	}

	/* Stats teaser */
	.home-stats {
		display: flex;
		align-items: center;
		gap: 3rem;
		padding-top: 2.5rem;
		padding-bottom: 3rem;
		border-top: 1px solid var(--border);
		flex-wrap: wrap;
	}

	.stat {
		display: flex;
		flex-direction: column;
		gap: 0.2rem;
	}

	.stat-num {
		font-family: 'Georgia', serif;
		font-size: 2rem;
		font-weight: 700;
		color: var(--amber);
	}

	.stat-label {
		font-size: 0.78rem;
		color: var(--text-muted);
		text-transform: uppercase;
		letter-spacing: 0.06em;
	}

	.stat-cta {
		margin-left: auto;
		font-size: 0.85rem;
		color: var(--amber);
	}

	.home-section {
		margin-bottom: 3rem;
	}

	@media (max-width: 900px) {
		.hero {
			grid-template-columns: 1fr;
		}
		.hero-recent {
			display: none;
		}
		.hero-featured {
			padding: 2rem 1.5rem;
		}
		.hero-poster {
			flex: 0 0 140px;
		}
		.hero-title {
			font-size: 1.5rem;
		}
	}

	@media (max-width: 640px) {
		.hero-poster {
			display: none;
		}
		.home-stats {
			gap: 2rem;
		}
		.stat-num {
			font-size: 1.5rem;
		}
	}
</style>

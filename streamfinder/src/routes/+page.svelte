<script lang="ts">
	import type { PageData } from './$types';
	import type { TitleIndex } from '$lib/types';
	import { base } from '$app/paths';
	import PosterCard from '$lib/components/PosterCard.svelte';
	import { platformColor } from '$lib/platforms';

	let { data }: { data: PageData } = $props();

	// Platforms surfaced in the "Podle platformy" section (in priority order).
	const PLATFORMS = ['Netflix', 'Disney+', 'HBO Max', 'Max', 'Prime Video', 'Apple TV+'];

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

	// ── Hero carousel ────────────────────────────────────────────────────
	const slides = data.featuredList;
	const SLIDE_MS = 6500;

	let current = $state(0);
	let paused = $state(false);

	function goTo(i: number) {
		current = (i + slides.length) % slides.length;
	}
	function next() {
		goTo(current + 1);
	}
	function prev() {
		goTo(current - 1);
	}

	// Auto-advance. The effect re-runs whenever `current` or `paused` changes, so the
	// timer restarts cleanly after a manual jump or a hover-pause. Respects
	// prefers-reduced-motion — no auto-rotation for viewers who opt out.
	$effect(() => {
		if (slides.length <= 1 || paused) return;
		if (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) return;
		current; // track, so the timer resets on every slide change
		const id = setTimeout(next, SLIDE_MS);
		return () => clearTimeout(id);
	});
</script>

<!-- Hero carousel -->
{#if slides.length > 0}
	<section
		class="hero"
		onmouseenter={() => (paused = true)}
		onmouseleave={() => (paused = false)}
		onfocusin={() => (paused = true)}
		onfocusout={() => (paused = false)}
		aria-roledescription="carousel"
		aria-label="Doporučené tituly"
	>
		{#each slides as f, i}
			<article class="hero-slide" class:active={i === current} inert={i !== current}>
				<div class="hero-bg" style="background-image:url({f.poster})"></div>
				<div class="hero-scrim"></div>
				<div class="hero-inner">
					<a href="{base}/titul/{f.id}/{f.slug}" class="hero-poster">
						<img src={f.poster} alt={f.title} loading={i === 0 ? 'eager' : 'lazy'} />
					</a>
					<div class="hero-info">
						<span class="kicker">Výběr redakce{#if f.genres.length} · {f.genres[0]}{/if}</span>
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
			</article>
		{/each}

		{#if slides.length > 1}
			<button class="hero-nav prev" onclick={prev} aria-label="Předchozí titul">‹</button>
			<button class="hero-nav next" onclick={next} aria-label="Další titul">›</button>

			<div class="hero-progress" role="tablist" aria-label="Přepínač titulů">
				{#each slides as f, i}
					<button
						class="seg"
						class:active={i === current}
						class:done={i < current}
						onclick={() => goTo(i)}
						role="tab"
						aria-selected={i === current}
						aria-label="{f.title} ({i + 1}/{slides.length})"
					>
						{#if i === current}
							{#key current}
								<span class="seg-fill" class:paused style="animation-duration:{SLIDE_MS}ms"></span>
							{/key}
						{/if}
					</button>
				{/each}
			</div>
		{/if}
	</section>

	<!-- Search strip — visible, not dominant -->
	<div class="search-strip">
		<div class="page-container search-strip-inner">
			<form class="home-search" action="{base}/katalog" method="GET">
				<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="8" /><path d="m21 21-4.3-4.3" /></svg>
				<input name="q" type="search" placeholder="Co chcete vidět? Film, seriál, herec…" aria-label="Hledat" />
			</form>
			<div class="home-chips">
				{#each ['Dokumentární', 'Thriller', 'Komedie', 'Drama'] as g}
					<a class="home-chip" href="{base}/katalog?genre={encodeURIComponent(g)}">{g}</a>
				{/each}
				{#each ['Netflix', 'Disney+', 'HBO Max'] as p}
					<a class="home-chip home-chip--brand" style="background:{platformColor(p)}" href="{base}/katalog?platform={encodeURIComponent(p)}">{p}</a>
				{/each}
			</div>
		</div>
	</div>
{:else}
	<section class="hero hero--empty">
		<div class="hero-empty">
			<p>Žádný doporučený titul momentálně není k dispozici.</p>
		</div>
	</section>
{/if}

<!-- Curated editorial rails -->
{#snippet rail(kicker: string, title: string, items: TitleIndex[], href: string, hrefLabel: string)}
	{#if items.length > 0}
		<section class="home-section page-container">
			<div class="rail-head">
				<div>
					<span class="kicker">{kicker}</span>
					<h2 class="rail-title">{title}</h2>
				</div>
				<a class="rail-all" {href}>{hrefLabel}</a>
			</div>
			<div class="scroll-row">
				{#each items as t (t.id)}
					<PosterCard title={t} />
				{/each}
			</div>
		</section>
	{/if}
{/snippet}

{@render rail('Posledních 7 dní', 'Právě přibylo', data.justAdded, `${base}/kalendar`, 'Celý kalendář →')}
{@render rail('Výběr redakce', 'Nejlíp hodnocené tento měsíc', data.bestThisMonth, `${base}/katalog?sort=rating`, 'Zobrazit vše →')}
{@render rail('Nové epizody každý týden', 'Seriály, co právě běží', data.runningSerials, `${base}/katalog?type=${encodeURIComponent('seriál')}`, 'Zobrazit vše →')}
{@render rail('80 %+ a málo vidění', 'Skryté klenoty', data.hiddenGems, `${base}/katalog?sort=rating`, 'Zobrazit vše →')}

<!-- Podle platformy -->
<section class="home-section page-container">
	<div class="rail-head">
		<div>
			<span class="kicker">Kde právě přibývá</span>
			<h2 class="rail-title">Podle platformy</h2>
		</div>
	</div>
	<div class="plat-grid">
		{#each PLATFORMS as p}
			{@const dim = data.dimensions.platforms.find((x) => x.name === p)}
			{#if dim}
				<a
					class="plat-tile"
					href="{base}/katalog?platform={encodeURIComponent(p)}"
					style="background:linear-gradient(160deg, {platformColor(p)}22, var(--navy-700))"
				>
					<span class="plat-glow" style="background:{platformColor(p)}"></span>
					<span class="plat-name">{p}</span>
					<span class="plat-count">{dim.count.toLocaleString('cs-CZ')} titulů →</span>
				</a>
			{/if}
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
	/* Hero carousel — cinematic stage */
	.hero {
		position: relative;
		min-height: 460px;
		overflow: hidden;
		background: var(--navy-900);
		border-bottom: 1px solid var(--border);
	}

	.hero--empty {
		min-height: 200px;
	}

	.hero-slide {
		position: absolute;
		inset: 0;
		opacity: 0;
		visibility: hidden;
		transition: opacity 0.7s ease;
	}

	.hero-slide.active {
		opacity: 1;
		visibility: visible;
	}

	/* Ambient blurred poster fills the stage and changes with each title */
	.hero-bg {
		position: absolute;
		inset: -12%; /* bleed so the blur's soft edges stay off-screen */
		background-size: cover;
		background-position: center 22%;
		filter: blur(38px) saturate(1.2) brightness(0.55);
		transform: scale(1.15);
	}

	.hero-scrim {
		position: absolute;
		inset: 0;
		background:
			linear-gradient(90deg, rgba(6, 11, 25, 0.94) 0%, rgba(6, 11, 25, 0.74) 45%, rgba(6, 11, 25, 0.5) 100%),
			linear-gradient(0deg, rgba(6, 11, 25, 0.85), transparent 55%);
	}

	.hero-inner {
		position: relative;
		display: flex;
		align-items: center;
		gap: 2.5rem;
		max-width: 1400px;
		margin: 0 auto;
		min-height: 460px;
		padding: 3rem 2.5rem 3.75rem;
	}

	.hero-poster {
		flex: 0 0 210px;
		display: block;
		border-radius: var(--radius);
		overflow: hidden;
		box-shadow: 0 24px 60px rgba(0, 0, 0, 0.7);
		transition: transform 0.25s;
	}

	.hero-poster:hover {
		transform: translateY(-4px);
	}

	.hero-poster img {
		width: 100%;
		display: block;
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
		font-family: 'Playfair Display', Georgia, serif;
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

	/* Carousel navigation arrows */
	.hero-nav {
		position: absolute;
		top: 50%;
		transform: translateY(-50%);
		z-index: 3;
		width: 44px;
		height: 44px;
		display: flex;
		align-items: center;
		justify-content: center;
		font-size: 1.8rem;
		line-height: 1;
		color: var(--text-secondary);
		background: rgba(8, 14, 30, 0.4);
		border: 1px solid rgba(255, 255, 255, 0.08);
		border-radius: 50%;
		cursor: pointer;
		opacity: 0;
		transition: opacity 0.2s, background 0.2s, color 0.2s;
	}

	.hero:hover .hero-nav {
		opacity: 1;
	}

	.hero-nav:hover {
		background: rgba(8, 14, 30, 0.78);
		color: var(--amber);
	}

	.hero-nav:focus-visible {
		opacity: 1;
		outline: 2px solid var(--amber);
		outline-offset: 2px;
	}

	.hero-nav.prev {
		left: 1rem;
	}
	.hero-nav.next {
		right: 1rem;
	}

	/* Segmented progress track — one bar per slide, active one fills as a timer */
	.hero-progress {
		position: absolute;
		bottom: 1.25rem;
		left: 2.5rem;
		z-index: 3;
		display: flex;
		gap: 0.5rem;
	}

	.seg {
		position: relative;
		width: 40px;
		height: 4px;
		padding: 0;
		border: none;
		border-radius: 2px;
		background: rgba(255, 255, 255, 0.2);
		cursor: pointer;
		overflow: hidden;
		transition: background 0.2s;
	}

	.seg:hover {
		background: rgba(255, 255, 255, 0.34);
	}

	.seg.done {
		background: rgba(255, 255, 255, 0.5);
	}

	.seg:focus-visible {
		outline: 2px solid var(--amber);
		outline-offset: 3px;
	}

	.seg-fill {
		position: absolute;
		inset: 0;
		background: var(--amber);
		transform-origin: left;
		transform: scaleX(0);
		animation: seg-fill linear forwards;
	}

	.seg-fill.paused {
		animation-play-state: paused;
	}

	@keyframes seg-fill {
		from {
			transform: scaleX(0);
		}
		to {
			transform: scaleX(1);
		}
	}

	/* Editorial kicker / eyebrow — states the curation rule */
	.kicker {
		display: inline-flex;
		align-items: center;
		gap: 0.6rem;
		font-size: 0.7rem;
		font-weight: 700;
		text-transform: uppercase;
		letter-spacing: 0.16em;
		color: var(--amber);
	}

	.kicker::before {
		content: '';
		width: 26px;
		height: 1px;
		background: var(--amber);
		opacity: 0.7;
	}

	.hero-info .kicker {
		margin-bottom: 0.9rem;
	}

	/* Rail heading */
	.rail-head {
		display: flex;
		align-items: flex-end;
		justify-content: space-between;
		gap: 1rem;
		margin-bottom: 1.25rem;
	}

	.rail-title {
		font-family: 'Playfair Display', Georgia, serif;
		font-weight: 700;
		font-size: clamp(1.4rem, 3vw, 1.85rem);
		letter-spacing: -0.01em;
		color: var(--text-primary);
		margin: 0.4rem 0 0;
	}

	.rail-all {
		font-size: 0.85rem;
		color: var(--amber);
		white-space: nowrap;
	}

	.rail-all:hover {
		text-decoration: underline;
		text-underline-offset: 3px;
	}

	/* Search strip — visible, not dominant */
	.search-strip {
		background: var(--navy-800);
		border-bottom: 1px solid var(--border);
	}

	.search-strip-inner {
		display: flex;
		align-items: center;
		gap: 1.2rem;
		padding-top: 1.1rem;
		padding-bottom: 1.1rem;
		flex-wrap: wrap;
	}

	.home-search {
		display: flex;
		align-items: center;
		gap: 0.7rem;
		flex: 1 1 340px;
		min-width: 240px;
		padding: 0.65rem 1rem;
		background: var(--navy-700);
		border: 1px solid var(--border);
		border-radius: 999px;
		color: var(--text-muted);
	}

	.home-search:focus-within {
		border-color: var(--amber);
	}

	.home-search input {
		flex: 1;
		min-width: 0;
		background: none;
		border: none;
		outline: none;
		color: var(--text-primary);
		font-size: 0.95rem;
		font-family: inherit;
	}

	.home-search input::placeholder {
		color: var(--text-secondary);
	}

	.home-chips {
		display: flex;
		gap: 0.5rem;
		flex-wrap: wrap;
	}

	.home-chip {
		padding: 0.4rem 0.9rem;
		border-radius: 999px;
		background: var(--navy-700);
		border: 1px solid var(--border);
		font-size: 0.82rem;
		color: var(--text-secondary);
		transition: border-color 0.15s, color 0.15s;
	}

	.home-chip:hover {
		border-color: var(--amber);
		color: var(--text-primary);
	}

	.home-chip--brand {
		color: #fff;
		border: none;
		font-weight: 600;
	}

	.home-chip--brand:hover {
		color: #fff;
		opacity: 0.88;
	}

	/* Podle platformy */
	.plat-grid {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
		gap: 1rem;
	}

	.plat-tile {
		position: relative;
		overflow: hidden;
		padding: 1.3rem 1.2rem;
		border-radius: 12px;
		border: 1px solid var(--border);
		min-height: 116px;
		display: flex;
		flex-direction: column;
		justify-content: space-between;
		transition: transform 0.2s, border-color 0.2s;
	}

	.plat-tile:hover {
		transform: translateY(-4px);
		border-color: rgba(255, 255, 255, 0.16);
	}

	.plat-glow {
		position: absolute;
		width: 160px;
		height: 160px;
		right: -40px;
		top: -50px;
		border-radius: 50%;
		filter: blur(30px);
		opacity: 0.5;
	}

	.plat-name {
		position: relative;
		font-family: 'Playfair Display', Georgia, serif;
		font-weight: 700;
		font-size: 1.2rem;
		color: var(--text-primary);
	}

	.plat-count {
		position: relative;
		font-size: 0.8rem;
		color: var(--text-secondary);
		font-variant-numeric: tabular-nums;
	}

	.hero-empty {
		padding: 3rem;
		color: var(--text-muted);
	}

	@media (prefers-reduced-motion: reduce) {
		.hero-slide {
			transition: none;
		}
		.seg-fill {
			animation: none;
			transform: scaleX(1);
		}
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
		font-family: 'Playfair Display', Georgia, serif;
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
		.hero,
		.hero-inner {
			min-height: 440px;
		}
		.hero-inner {
			padding: 2rem 1.5rem 3.25rem;
			gap: 1.5rem;
		}
		.hero-poster {
			flex: 0 0 140px;
		}
		.hero-title {
			font-size: 1.5rem;
		}
		.hero-progress {
			left: 1.5rem;
		}
	}

	@media (max-width: 640px) {
		.hero,
		.hero-inner {
			min-height: 400px;
		}
		.hero-poster {
			display: none;
		}
		.hero-scrim {
			background: linear-gradient(0deg, rgba(6, 11, 25, 0.94), rgba(6, 11, 25, 0.5));
		}
		.hero-nav {
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

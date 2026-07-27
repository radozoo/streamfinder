<script lang="ts">
	import type { PageData } from './$types';
	import { base } from '$app/paths';
	import { platformSearchUrl } from '$lib/platforms';
	import {
		ratingColor,
		shapeText as buildShapeText,
		buildSeasons,
		dotPos,
		shortDate,
		cadenceLabel
	} from '$lib/format';

	let { data }: { data: PageData } = $props();
	let t = $derived(data.title);

	// Serial shape ("2 série · 18 epizod") + availability timeline — same
	// derivation as TitleModal, so a series describes itself identically
	// whether opened from a card modal or its own page.
	let shapeText = $derived.by(() => buildShapeText(t));
	let seasons = $derived.by(() => buildSeasons(t.episodes));

	function formatRuntime(min: number | null) {
		if (!min) return null;
		const h = Math.floor(min / 60);
		const m = min % 60;
		return h > 0 ? `${h}h ${m}min` : `${m}min`;
	}

	function formatDate(d: string | null) {
		if (!d) return null;
		const [y, mo, day] = d.split('-');
		return `${day}. ${mo}. ${y}`;
	}
</script>

<svelte:head>
	<title>{t.title} ({t.year ?? '?'}) — Streamfinder</title>
	{#if t.plot}
		<meta name="description" content={t.plot.slice(0, 160)} />
		<meta property="og:description" content={t.plot.slice(0, 160)} />
	{/if}
	<meta property="og:title" content="{t.title} ({t.year ?? '?'})" />
	<meta property="og:type" content="video.movie" />
	{#if t.poster}
		<meta property="og:image" content={t.poster} />
	{/if}
</svelte:head>

<!-- Backdrop hero -->
{#if t.backdrop}
	<div class="hero">
		<img class="hero-img" src={t.backdrop} alt="" />
		<div class="hero-fade"></div>
	</div>
{/if}

<div class="page-container detail-page">
	<div class="detail-top">
		<!-- Poster -->
		{#if t.poster}
			<img class="detail-poster" class:overlap={!!t.backdrop} src={t.poster} alt={t.title} />
		{:else}
			<div class="detail-poster-placeholder" class:overlap={!!t.backdrop}>{t.title}</div>
		{/if}

		<!-- Main info -->
		<div class="detail-info">
			<div class="breadcrumb">
				<a href="{base}/katalog">Katalog</a>
				<span>›</span>
				{#if t.genres.length}
					<a href="{base}/katalog?genre={t.genres[0]}">{t.genres[0]}</a>
					<span>›</span>
				{/if}
				<span class="breadcrumb-current">{t.title}</span>
			</div>

			<h1 class="detail-title">{t.title}</h1>
			{#if t.title_en && t.title_en !== t.title}
				<p class="detail-title-en">{t.title_en}</p>
			{/if}

			<!-- Meta row -->
			<div class="meta-row">
				{#if t.rating !== null}
					<span class="big-rating" style="color: {ratingColor(t.rating)}">{t.rating} %</span>
				{/if}
				{#if t.votes_count}
					<span class="meta-muted">({t.votes_count.toLocaleString('cs')} hodnocení)</span>
				{/if}
				{#if t.year}
					<span class="meta-muted">{t.year}</span>
				{/if}
				{#if t.runtime_min}
					<span class="meta-muted">{formatRuntime(t.runtime_min)}</span>
				{/if}
				{#if t.title_type && t.title_type !== 'film'}
					<span class="type-badge">{t.title_type}</span>
				{/if}
				{#if t.age_rating}
					<span class="age-badge">{t.age_rating}</span>
				{/if}
			</div>

			{#if shapeText}
				<div class="shape-row">
					<span class="shape-text">{shapeText}</span>
					{#if t.is_running}<span class="shape-live">● běží</span>{/if}
				</div>
			{/if}

			<!-- Genres + countries -->
			<div class="tag-row">
				{#each t.genres as g}
					<a class="pill" href="{base}/katalog?genre={g}">{g}</a>
				{/each}
				{#each t.countries as c}
					<span class="pill country-pill">{c}</span>
				{/each}
			</div>

			<!-- Plot -->
			{#if t.plot}
				<p class="detail-plot">{t.plot}</p>
			{/if}

			<!-- VOD links -->
			{#if t.vods.length}
				<div class="vod-actions">
					{#each t.vods as vod}
						{@const href = vod.url ?? platformSearchUrl(vod.platform, t.title_en || t.title)}
						{#if href}
							<a class="vod-btn" {href} target="_blank" rel="noopener noreferrer">
								▶ Sledovat na {vod.platform}
							</a>
						{:else}
							<span class="vod-badge-large">{vod.platform}</span>
						{/if}
					{/each}
				</div>
			{/if}

			{#if t.vod_date}
				<p class="vod-date">Na VOD od {formatDate(t.vod_date)}</p>
			{/if}

			<!-- CSFD link -->
			{#if t.link}
				<a class="csfd-link" href={t.link} target="_blank" rel="noopener noreferrer">
					Otevřít na ČSFD →
				</a>
			{/if}
		</div>
	</div>

	<!-- Crew section -->
	<div class="detail-sections">
		{#if seasons.length}
			<section class="timeline-section">
				<div class="tl-head">
					<h2 class="section-title">Časová osa dostupnosti</h2>
					{#if cadenceLabel(t.cadence_days)}
						<span class="tl-cad">{cadenceLabel(t.cadence_days)}</span>
					{/if}
				</div>
				{#each seasons as s}
					<div class="tl-season">
						<div class="tl-slabel">
							<span class="tl-sname">{s.season ? `SÉRIE ${s.season}` : 'EPIZODY'}</span>
							<span class="tl-dates">
								{shortDate(s.first)}–{shortDate(s.last)} ·
								{s.eps.length} {s.eps.length === 1 ? 'epizoda' : s.eps.length < 5 ? 'epizody' : 'epizod'}
							</span>
						</div>
						<div class="tl-track">
							<div class="tl-line"></div>
							{#each s.eps as e}
								<span
									class="tl-dot"
									style="left: {dotPos(e, s.first, s.last)}%"
									title={`${e.title} · ${shortDate(e.vod_date)}`}
								></span>
							{/each}
						</div>
					</div>
				{/each}
			</section>
		{/if}

		{#if t.directors.length || t.actors.length || t.screenwriters.length || t.cinematographers.length || t.composers.length}
			<section class="crew-section">
				<h2 class="section-title">Tvůrci</h2>
				<dl class="crew-list">
					{#if t.directors.length}
						<div class="crew-row">
							<dt>Režie</dt>
							<dd>{t.directors.join(', ')}</dd>
						</div>
					{/if}
					{#if t.screenwriters.length}
						<div class="crew-row">
							<dt>Scénář</dt>
							<dd>{t.screenwriters.join(', ')}</dd>
						</div>
					{/if}
					{#if t.cinematographers.length}
						<div class="crew-row">
							<dt>Kamera</dt>
							<dd>{t.cinematographers.join(', ')}</dd>
						</div>
					{/if}
					{#if t.composers.length}
						<div class="crew-row">
							<dt>Hudba</dt>
							<dd>{t.composers.join(', ')}</dd>
						</div>
					{/if}
					{#if t.actors.length}
						<div class="crew-row">
							<dt>Hrají</dt>
							<dd>{t.actors.join(', ')}</dd>
						</div>
					{/if}
				</dl>
			</section>
		{/if}

		<!-- Trailer -->
		{#if t.trailer_youtube_id}
			<section class="trailer-section">
				<h2 class="section-title">Trailer</h2>
				<div class="trailer-wrap">
					<iframe
						src="https://www.youtube.com/embed/{t.trailer_youtube_id}"
						title="Trailer — {t.title}"
						frameborder="0"
						allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
						allowfullscreen
					></iframe>
				</div>
			</section>
		{/if}

		<!-- Reviews -->
		{#if t.reviews.length}
			<section class="reviews-section">
				<h2 class="section-title">Recenze</h2>
				<div class="reviews-list">
					{#each t.reviews as review}
						<div class="review-card">
							<div class="review-header">
								{#if review.stars !== null}
									<div class="stars">{'★'.repeat(review.stars)}{'☆'.repeat(5 - review.stars)}</div>
								{/if}
								{#if review.author}
									<span class="review-author">{review.author}</span>
								{/if}
							</div>
							{#if review.text}
								<p class="review-text">{review.text}</p>
							{/if}
						</div>
					{/each}
				</div>
			</section>
		{/if}
	</div>

	<!-- Back link -->
	<a class="back-link" href="{base}/katalog">← Zpět do katalogu</a>
</div>

<style>
	.hero {
		position: relative;
		height: 380px;
		overflow: hidden;
		margin-top: -0px;
	}

	.hero-img {
		width: 100%;
		height: 100%;
		object-fit: cover;
		object-position: center 25%;
	}

	.hero-fade {
		position: absolute;
		inset: 0;
		background: linear-gradient(to bottom, rgba(8,14,30,0.2) 0%, var(--navy-900) 100%);
	}

	.detail-page {
		/* .page-container's 1400px suits grid pages (Katalog); this page is a
		   text column that never gets close to that width. Cap and center it
		   locally so the leftover space reads as a deliberate margin on both
		   sides, not a lopsided gap on the right. */
		max-width: 1100px;
		margin: 0 auto;
		padding-top: 1.5rem;
	}

	.detail-top {
		display: flex;
		gap: 2rem;
		align-items: flex-start;
		margin-bottom: 3rem;
	}

	@media (max-width: 640px) {
		.detail-top {
			flex-direction: column;
		}
		.hero {
			height: 200px;
		}
	}

	.detail-poster {
		width: 180px;
		min-width: 180px;
		border-radius: var(--radius);
		object-fit: cover;
		position: relative;
		z-index: 1;
		box-shadow: 0 12px 40px rgba(0,0,0,0.6);
	}

	.detail-poster-placeholder {
		width: 180px;
		min-width: 180px;
		aspect-ratio: 2/3;
		background: var(--navy-700);
		border-radius: var(--radius);
		display: flex;
		align-items: center;
		justify-content: center;
		color: var(--text-muted);
		font-size: 0.8rem;
		padding: 1rem;
		text-align: center;
	}

	/* Only pull the poster up to overlap the backdrop hero when one is actually
	   rendered — without it there is no 380px hero to compensate for the
	   negative margin, which used to clip the poster's top under the nav. */
	.detail-poster.overlap,
	.detail-poster-placeholder.overlap {
		margin-top: -100px;
	}

	.breadcrumb {
		display: flex;
		align-items: center;
		gap: 0.4rem;
		font-size: 0.8rem;
		color: var(--text-muted);
		margin-bottom: 0.5rem;
	}

	.breadcrumb a {
		color: var(--amber);
	}

	.breadcrumb-current {
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.detail-title {
		font-family: 'Georgia', serif;
		font-size: 2rem;
		line-height: 1.2;
		margin-bottom: 0.25rem;
	}

	@media (max-width: 640px) {
		.detail-title {
			font-size: 1.4rem;
		}
	}

	.detail-title-en {
		color: var(--text-muted);
		font-size: 1rem;
		margin-bottom: 0.75rem;
	}

	.meta-row {
		display: flex;
		align-items: center;
		flex-wrap: wrap;
		gap: 0.6rem;
		margin-bottom: 0.75rem;
	}

	.big-rating {
		font-size: 1.5rem;
		font-weight: 700;
	}

	.meta-muted {
		color: var(--text-muted);
		font-size: 0.9rem;
	}

	.type-badge, .age-badge {
		font-size: 0.75rem;
		padding: 2px 8px;
		border-radius: 999px;
		background: var(--navy-600);
	}

	.age-badge {
		color: #e57373;
	}

	.tag-row {
		display: flex;
		flex-wrap: wrap;
		gap: 0.4rem;
		margin-bottom: 1rem;
	}

	.country-pill {
		opacity: 0.6;
	}

	.detail-plot {
		color: var(--text-secondary);
		line-height: 1.7;
		margin-bottom: 1.25rem;
		max-width: 60ch;
	}

	.vod-actions {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem;
		margin-bottom: 0.75rem;
	}

	.vod-btn {
		display: inline-flex;
		align-items: center;
		gap: 0.4rem;
		padding: 0.55rem 1.25rem;
		background: var(--amber);
		color: var(--navy-900);
		font-weight: 700;
		font-size: 0.9rem;
		border-radius: var(--radius-sm);
		text-decoration: none;
		transition: opacity 0.15s;
	}

	.vod-btn:hover {
		opacity: 0.85;
	}

	.vod-badge-large {
		display: inline-block;
		padding: 0.55rem 1rem;
		background: var(--navy-600);
		border-radius: var(--radius-sm);
		font-size: 0.85rem;
		color: var(--text-secondary);
	}

	.vod-date {
		font-size: 0.8rem;
		color: var(--text-muted);
		margin-bottom: 0.5rem;
	}

	/* Serial shape line — same treatment as the card modal */
	.shape-row {
		display: flex;
		align-items: center;
		gap: 0.6rem;
		margin-bottom: 1rem;
	}

	.shape-text {
		font-size: 0.95rem;
		font-weight: 600;
		color: var(--amber);
	}

	.shape-live {
		font-size: 0.72rem;
		font-weight: 700;
		letter-spacing: 0.04em;
		text-transform: uppercase;
		padding: 2px 8px;
		border-radius: 999px;
		background: rgba(74, 222, 128, 0.16);
		color: #4ade80;
		border: 1px solid rgba(74, 222, 128, 0.35);
	}

	/* Release timeline */
	.tl-head {
		display: flex;
		align-items: baseline;
		gap: 0.6rem;
		margin-bottom: 1rem;
	}

	.tl-cad {
		margin-left: auto;
		font-size: 0.75rem;
		color: #4ade80;
	}

	.tl-season {
		margin-bottom: 1.1rem;
	}

	.tl-slabel {
		display: flex;
		align-items: baseline;
		gap: 0.6rem;
		margin-bottom: 0.6rem;
		flex-wrap: wrap;
	}

	.tl-sname {
		font-family: ui-monospace, 'SF Mono', Menlo, monospace;
		font-size: 0.75rem;
		color: var(--amber);
		font-weight: 700;
	}

	.tl-dates {
		font-size: 0.75rem;
		color: var(--text-muted);
	}

	.tl-track {
		position: relative;
		height: 22px;
	}

	.tl-line {
		position: absolute;
		top: 10px;
		left: 0;
		right: 0;
		height: 2px;
		background: var(--navy-500);
		border-radius: 2px;
	}

	.tl-dot {
		position: absolute;
		top: 5px;
		width: 10px;
		height: 10px;
		border-radius: 50%;
		background: var(--amber);
		transform: translateX(-50%);
		border: 2px solid var(--navy-800);
		cursor: help;
	}

	.csfd-link {
		display: inline-block;
		color: var(--text-muted);
		font-size: 0.8rem;
		margin-top: 0.5rem;
	}

	.csfd-link:hover {
		color: var(--amber);
	}

	.detail-sections {
		display: flex;
		flex-direction: column;
		gap: 2.5rem;
		max-width: 900px;
	}

	/* Crew */
	.crew-section {}

	.crew-list {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}

	.crew-row {
		display: grid;
		grid-template-columns: 100px 1fr;
		gap: 0.5rem;
	}

	.crew-row dt {
		color: var(--text-muted);
		font-size: 0.85rem;
	}

	.crew-row dd {
		color: var(--text-secondary);
		font-size: 0.85rem;
	}

	/* Trailer */
	.trailer-wrap {
		border-radius: var(--radius);
		overflow: hidden;
		max-width: 640px;
	}

	.trailer-wrap iframe {
		width: 100%;
		aspect-ratio: 16/9;
		display: block;
	}

	/* Reviews */
	.reviews-list {
		display: flex;
		flex-direction: column;
		gap: 1rem;
	}

	.review-card {
		background: var(--navy-700);
		border-radius: var(--radius);
		padding: 1rem 1.25rem;
		border: 1px solid var(--border);
	}

	.review-header {
		display: flex;
		align-items: center;
		gap: 0.6rem;
		margin-bottom: 0.5rem;
	}

	.review-author {
		font-size: 0.85rem;
		font-weight: 600;
		color: var(--text-secondary);
	}

	.review-text {
		color: var(--text-muted);
		font-size: 0.9rem;
		line-height: 1.65;
	}

	.back-link {
		display: inline-block;
		margin-top: 3rem;
		color: var(--text-muted);
		font-size: 0.85rem;
		text-decoration: none;
	}

	.back-link:hover {
		color: var(--amber);
	}
</style>

<script lang="ts">
	import type { PageData } from './$types';
	import type { TitleIndex, TitleDetail } from '$lib/types';
	import PosterCard from '$lib/components/PosterCard.svelte';
	import { base } from '$app/paths';

	let { data }: { data: PageData } = $props();

	// ── Filter state ──────────────────────────────────────────────────────────
	let searchQuery = $state('');
	let selectedGenres = $state<string[]>([]);
	let selectedPlatforms = $state<string[]>([]);
	let selectedCountries = $state<string[]>([]);
	let selectedType = $state<string>('');
	let yearFrom = $state<number | ''>('');
	let yearTo = $state<number | ''>('');
	let ratingMin = $state<number | ''>('');
	let sortBy = $state<'rating' | 'year' | 'vod_date' | 'votes'>('vod_date');

	// ── Modal state ───────────────────────────────────────────────────────────
	let modalTitle = $state<TitleDetail | null>(null);
	let modalLoading = $state(false);

	// ── Filtered + sorted titles ──────────────────────────────────────────────
	let filtered = $derived.by(() => {
		const q = searchQuery.trim().toLowerCase();
		return data.titles
			.filter((t) => {
				if (q && !t.title.toLowerCase().includes(q) && !(t.title_en ?? '').toLowerCase().includes(q)) return false;
				if (selectedGenres.length && !selectedGenres.some((g) => t.genres.includes(g))) return false;
				if (selectedPlatforms.length && !selectedPlatforms.some((p) => t.platforms.includes(p))) return false;
				if (selectedCountries.length && !selectedCountries.some((c) => t.countries.includes(c))) return false;
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
				// vod_date desc
				return (b.vod_date ?? '').localeCompare(a.vod_date ?? '');
			});
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

	// ── Types from data ───────────────────────────────────────────────────────
	let typeOptions = $derived(
		['film', 'seriál', 'tv film', 'pořad', 'krátký film']
			.filter((type) => data.titles.some((t) => t.title_type === type))
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

	function clearAll() {
		searchQuery = '';
		selectedGenres = [];
		selectedPlatforms = [];
		selectedCountries = [];
		selectedType = '';
		yearFrom = '';
		yearTo = '';
		ratingMin = '';
	}

	let hasFilters = $derived(
		searchQuery.trim() !== '' ||
			selectedGenres.length > 0 ||
			selectedPlatforms.length > 0 ||
			selectedCountries.length > 0 ||
			selectedType !== '' ||
			yearFrom !== '' ||
			yearTo !== '' ||
			ratingMin !== ''
	);

	// ── Modal ─────────────────────────────────────────────────────────────────
	async function openModal(t: TitleIndex) {
		modalLoading = true;
		modalTitle = null;
		try {
			const res = await fetch(`${base}/data/titles_detail.json`);
			const detail: Record<string, TitleDetail> = await res.json();
			const key = `${t.id}-${t.slug}`;
			modalTitle = detail[key] ?? { ...t, plot: null, backdrop: null, trailer_youtube_id: null, age_rating: null, directors: [], actors: [], screenwriters: [], cinematographers: [], composers: [], reviews: [], vods: [] };
		} catch {
			modalTitle = { ...t, plot: null, backdrop: null, trailer_youtube_id: null, age_rating: null, directors: [], actors: [], screenwriters: [], cinematographers: [], composers: [], reviews: [], vods: [] };
		} finally {
			modalLoading = false;
		}
	}

	function closeModal() {
		modalTitle = null;
		modalLoading = false;
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Escape') closeModal();
	}

	function ratingColor(r: number | null) {
		if (!r) return 'var(--text-muted)';
		if (r >= 70) return '#4caf50';
		if (r >= 50) return 'var(--amber)';
		return '#e57373';
	}

	// initial genre from URL (passed by +page.ts)
	$effect(() => {
		if (data.initialGenre && !selectedGenres.includes(data.initialGenre)) {
			selectedGenres = [data.initialGenre];
		}
	});
</script>

<svelte:window onkeydown={handleKeydown} />

<div class="page-container">
	<!-- Header row -->
	<div class="katalog-header">
		<h1 class="section-title">Katalog</h1>
		<div class="result-count">
			{filtered.length} {filtered.length === 1 ? 'titul' : filtered.length < 5 ? 'tituly' : 'titulů'}
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
		<!-- Sidebar filters -->
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
					{#each filtered as title (title.id)}
						<PosterCard {title} onclick={openModal} />
					{/each}
				</div>
			{/if}
		</section>
	</div>
</div>

<!-- Modal overlay -->
{#if modalLoading || modalTitle}
	<div class="modal-overlay" onclick={closeModal} role="dialog" aria-modal="true">
		<div class="modal" onclick={(e) => e.stopPropagation()}>
			<button class="modal-close" onclick={closeModal} aria-label="Zavřít">✕</button>

			{#if modalLoading}
				<div class="modal-loading">Načítám…</div>
			{:else if modalTitle}
				{#if modalTitle.backdrop}
					<div class="modal-backdrop">
						<img src={modalTitle.backdrop} alt="" />
						<div class="backdrop-fade"></div>
					</div>
				{/if}

				<div class="modal-content">
					<div class="modal-top">
						{#if modalTitle.poster}
							<img class="modal-poster" src={modalTitle.poster} alt={modalTitle.title} />
						{/if}

						<div class="modal-info">
							<h2 class="modal-title">{modalTitle.title}</h2>
							{#if modalTitle.title_en && modalTitle.title_en !== modalTitle.title}
								<p class="modal-title-en">{modalTitle.title_en}</p>
							{/if}

							<div class="modal-meta-row">
								{#if modalTitle.rating !== null}
									<span class="modal-rating" style="color: {ratingColor(modalTitle.rating)}">
										{modalTitle.rating} %
									</span>
								{/if}
								{#if modalTitle.year}
									<span class="meta-sep">{modalTitle.year}</span>
								{/if}
								{#if modalTitle.runtime_min}
									<span class="meta-sep">{Math.floor(modalTitle.runtime_min / 60)}h {modalTitle.runtime_min % 60}min</span>
								{/if}
								{#if modalTitle.title_type}
									<span class="meta-sep type-badge">{modalTitle.title_type}</span>
								{/if}
								{#if modalTitle.age_rating}
									<span class="meta-sep age-badge">{modalTitle.age_rating}</span>
								{/if}
							</div>

							{#if modalTitle.genres.length}
								<div class="modal-genres">
									{#each modalTitle.genres as g}
										<span class="pill">{g}</span>
									{/each}
								</div>
							{/if}

							{#if modalTitle.plot}
								<p class="modal-plot">{modalTitle.plot}</p>
							{/if}

							{#if modalTitle.directors.length}
								<p class="modal-crew"><strong>Režie:</strong> {modalTitle.directors.join(', ')}</p>
							{/if}
							{#if modalTitle.actors.length}
								<p class="modal-crew"><strong>Hrají:</strong> {modalTitle.actors.slice(0, 6).join(', ')}</p>
							{/if}

							<!-- VOD links -->
							{#if modalTitle.vods.length}
								<div class="modal-vods">
									{#each modalTitle.vods as vod}
										{#if vod.url}
											<a class="vod-btn" href={vod.url} target="_blank" rel="noopener noreferrer">
												▶ {vod.platform}
											</a>
										{:else}
											<span class="vod-badge">{vod.platform}</span>
										{/if}
									{/each}
								</div>
							{/if}

							<a class="detail-link" href="{base}/titul/{modalTitle.id}/{modalTitle.slug}">
								Zobrazit detail →
							</a>
						</div>
					</div>

					<!-- Trailer -->
					{#if modalTitle.trailer_youtube_id}
						<div class="modal-trailer">
							<iframe
								src="https://www.youtube.com/embed/{modalTitle.trailer_youtube_id}"
								title="Trailer"
								frameborder="0"
								allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
								allowfullscreen
							></iframe>
						</div>
					{/if}

					<!-- Reviews -->
					{#if modalTitle.reviews.length}
						<div class="modal-reviews">
							<h3 class="filter-label">Recenze</h3>
							{#each modalTitle.reviews.slice(0, 2) as review}
								<div class="review-item">
									{#if review.stars !== null}
										<div class="stars">{'★'.repeat(review.stars)}{'☆'.repeat(5 - review.stars)}</div>
									{/if}
									{#if review.author}
										<span class="review-author">{review.author}</span>
									{/if}
									{#if review.text}
										<p class="review-text">{review.text.slice(0, 280)}{review.text.length > 280 ? '…' : ''}</p>
									{/if}
								</div>
							{/each}
						</div>
					{/if}
				</div>
			{/if}
		</div>
	</div>
{/if}

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

	@media (max-width: 900px) {
		.katalog-body {
			grid-template-columns: 1fr;
		}
		.sidebar {
			display: grid;
			grid-template-columns: repeat(2, 1fr);
			gap: 1rem;
		}
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

	/* Grid */
	.grid-area {}

	.poster-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
		gap: 1rem;
	}

	@media (max-width: 640px) {
		.poster-grid {
			grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
		}
	}

	.empty-state {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 1rem;
		padding: 4rem 0;
		color: var(--text-muted);
	}

	/* Modal */
	.modal-overlay {
		position: fixed;
		inset: 0;
		background: rgba(0, 0, 0, 0.75);
		z-index: 200;
		display: flex;
		align-items: center;
		justify-content: center;
		padding: 1rem;
		backdrop-filter: blur(4px);
	}

	.modal {
		background: var(--navy-800);
		border-radius: var(--radius);
		border: 1px solid var(--border);
		width: 100%;
		max-width: 820px;
		max-height: 90vh;
		overflow-y: auto;
		position: relative;
		scrollbar-width: thin;
		scrollbar-color: var(--navy-500) transparent;
	}

	.modal-close {
		position: sticky;
		top: 0.75rem;
		float: right;
		margin: 0.75rem 0.75rem 0 0;
		background: rgba(0,0,0,0.5);
		border: none;
		border-radius: 50%;
		width: 32px;
		height: 32px;
		color: var(--text-primary);
		font-size: 0.9rem;
		cursor: pointer;
		z-index: 10;
		display: flex;
		align-items: center;
		justify-content: center;
	}

	.modal-loading {
		padding: 4rem;
		text-align: center;
		color: var(--text-muted);
	}

	.modal-backdrop {
		position: relative;
		height: 200px;
		overflow: hidden;
		border-radius: var(--radius) var(--radius) 0 0;
	}

	.modal-backdrop img {
		width: 100%;
		height: 100%;
		object-fit: cover;
		object-position: center 30%;
	}

	.backdrop-fade {
		position: absolute;
		inset: 0;
		background: linear-gradient(to bottom, transparent 30%, var(--navy-800));
	}

	.modal-content {
		padding: 1.5rem;
	}

	.modal-top {
		display: flex;
		gap: 1.5rem;
		margin-bottom: 1.25rem;
	}

	.modal-poster {
		width: 110px;
		min-width: 110px;
		border-radius: var(--radius-sm);
		object-fit: cover;
		margin-top: -60px;
		position: relative;
		z-index: 1;
		box-shadow: 0 8px 24px rgba(0,0,0,0.5);
	}

	.modal-title {
		font-family: 'Georgia', serif;
		font-size: 1.4rem;
		line-height: 1.2;
		margin-bottom: 0.25rem;
	}

	.modal-title-en {
		color: var(--text-muted);
		font-size: 0.85rem;
		margin-bottom: 0.5rem;
	}

	.modal-meta-row {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		flex-wrap: wrap;
		margin-bottom: 0.75rem;
		font-size: 0.85rem;
	}

	.modal-rating {
		font-weight: 700;
		font-size: 1rem;
	}

	.meta-sep {
		color: var(--text-muted);
	}

	.type-badge {
		background: var(--navy-600);
		padding: 2px 8px;
		border-radius: 999px;
		font-size: 0.75rem;
		color: var(--text-secondary);
	}

	.age-badge {
		background: var(--navy-600);
		padding: 2px 8px;
		border-radius: 999px;
		font-size: 0.75rem;
		color: #e57373;
	}

	.modal-genres {
		display: flex;
		flex-wrap: wrap;
		gap: 0.4rem;
		margin-bottom: 0.75rem;
	}

	.modal-plot {
		color: var(--text-secondary);
		font-size: 0.9rem;
		line-height: 1.6;
		margin-bottom: 0.75rem;
	}

	.modal-crew {
		font-size: 0.85rem;
		color: var(--text-muted);
		margin-bottom: 0.35rem;
	}

	.modal-crew strong {
		color: var(--text-secondary);
	}

	.modal-vods {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem;
		margin-top: 1rem;
	}

	.vod-btn {
		display: inline-flex;
		align-items: center;
		gap: 0.35rem;
		padding: 0.45rem 1rem;
		background: var(--amber);
		color: var(--navy-900);
		font-weight: 700;
		font-size: 0.85rem;
		border-radius: var(--radius-sm);
		text-decoration: none;
		transition: opacity 0.15s;
	}

	.vod-btn:hover {
		opacity: 0.85;
	}

	.detail-link {
		display: inline-block;
		margin-top: 1rem;
		color: var(--amber);
		font-size: 0.85rem;
		text-decoration: none;
	}

	.detail-link:hover {
		text-decoration: underline;
	}

	.modal-trailer {
		margin-top: 1rem;
		border-radius: var(--radius-sm);
		overflow: hidden;
	}

	.modal-trailer iframe {
		width: 100%;
		aspect-ratio: 16/9;
		display: block;
	}

	.modal-reviews {
		margin-top: 1.5rem;
		display: flex;
		flex-direction: column;
		gap: 1rem;
	}

	.review-item {
		background: var(--navy-700);
		border-radius: var(--radius-sm);
		padding: 0.75rem 1rem;
	}

	.review-author {
		font-size: 0.8rem;
		font-weight: 600;
		color: var(--text-secondary);
		margin-left: 0.5rem;
	}

	.review-text {
		font-size: 0.85rem;
		color: var(--text-muted);
		margin-top: 0.4rem;
		line-height: 1.55;
	}
</style>

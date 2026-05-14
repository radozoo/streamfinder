<script lang="ts">
	import type { TitleDetail } from '$lib/types';
	import { base } from '$app/paths';

	interface Props {
		title: TitleDetail | null;
		loading: boolean;
		onclose: () => void;
	}

	let { title, loading, onclose }: Props = $props();

	function ratingColor(r: number | null) {
		if (!r) return 'var(--text-muted)';
		if (r >= 70) return '#4caf50';
		if (r >= 50) return 'var(--amber)';
		return '#e57373';
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Escape') onclose();
	}
</script>

<svelte:window onkeydown={handleKeydown} />

{#if loading || title}
	<div
		class="modal-overlay"
		onclick={onclose}
		role="dialog"
		aria-modal="true"
		aria-label="Detail titulu"
		tabindex="-1"
	>
		<div class="modal" onclick={(e) => e.stopPropagation()} role="presentation">
			<button class="modal-close" onclick={onclose} aria-label="Zavřít">✕</button>

			{#if loading}
				<div class="modal-loading">Načítám…</div>
			{:else if title}
				{#if title.backdrop}
					<div class="modal-backdrop">
						<img src={title.backdrop} alt="" />
						<div class="backdrop-fade"></div>
					</div>
				{/if}

				<div class="modal-content">
					<div class="modal-top">
						{#if title.poster}
							<img class="modal-poster" src={title.poster} alt={title.title} />
						{/if}

						<div class="modal-info">
							<h2 class="modal-title">{title.title}</h2>
							{#if title.title_en && title.title_en !== title.title}
								<p class="modal-title-en">{title.title_en}</p>
							{/if}

							<div class="modal-meta-row">
								{#if title.rating !== null}
									<span class="modal-rating" style="color: {ratingColor(title.rating)}">
										{title.rating} %
									</span>
								{/if}
								{#if title.year}
									<span class="meta-sep">{title.year}</span>
								{/if}
								{#if title.runtime_min}
									<span class="meta-sep">{Math.floor(title.runtime_min / 60)}h {title.runtime_min % 60}min</span>
								{/if}
								{#if title.title_type}
									<span class="meta-sep type-badge">{title.title_type}</span>
								{/if}
								{#if title.age_rating}
									<span class="meta-sep age-badge">{title.age_rating}</span>
								{/if}
							</div>

							{#if title.genres.length}
								<div class="modal-genres">
									{#each title.genres as g}
										<span class="pill">{g}</span>
									{/each}
								</div>
							{/if}

							{#if title.plot}
								<p class="modal-plot">{title.plot}</p>
							{/if}

							{#if title.directors.length}
								<p class="modal-crew"><strong>Režie:</strong> {title.directors.join(', ')}</p>
							{/if}
							{#if title.actors.length}
								<p class="modal-crew"><strong>Hrají:</strong> {title.actors.slice(0, 6).join(', ')}</p>
							{/if}

							{#if title.vods.length}
								<div class="modal-vods">
									{#each title.vods as vod}
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

							<a class="detail-link" href="{base}/titul/{title.id}/{title.slug}">
								Zobrazit detail →
							</a>
						</div>
					</div>

					{#if title.trailer_youtube_id}
						<div class="modal-trailer">
							<iframe
								src="https://www.youtube.com/embed/{title.trailer_youtube_id}"
								title="Trailer"
								frameborder="0"
								allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
								allowfullscreen
							></iframe>
						</div>
					{/if}

					{#if title.reviews.length}
						<div class="modal-reviews">
							<h3 class="filter-label">Recenze</h3>
							{#each title.reviews.slice(0, 2) as review}
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
		background: rgba(0, 0, 0, 0.5);
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
		box-shadow: 0 8px 24px rgba(0, 0, 0, 0.5);
	}

	.modal-title {
		font-family: 'Playfair Display', Georgia, serif;
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

	.filter-label {
		font-size: 0.7rem;
		font-weight: 700;
		letter-spacing: 0.08em;
		text-transform: uppercase;
		color: var(--text-muted);
		margin-bottom: 0.5rem;
	}
</style>

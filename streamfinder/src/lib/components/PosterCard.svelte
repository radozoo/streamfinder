<script lang="ts">
	import type { TitleIndex } from '$lib/types';
	import { base } from '$app/paths';

	let { title, onclick }: { title: TitleIndex; onclick?: (t: TitleIndex) => void } = $props();

	// title_type is already a display label (seriál, pořad, tv film…). Films are the
	// default/majority → no badge, so the tag only appears where it carries information.
	let typeLabel = $derived(
		title.title_type && title.title_type !== 'film' ? title.title_type : null
	);

	// Primary genre(s) only — a quiet subtitle, never the full list
	let genreLine = $derived(title.genres.slice(0, 2).join(' · '));

	function handleClick() {
		if (onclick) onclick(title);
	}
</script>

{#snippet cardBody()}
	<div class="poster-media">
		{#if title.poster}
			<img src={title.poster} alt={title.title} loading="lazy" />
		{:else}
			<div class="poster-placeholder">{title.title}</div>
		{/if}

		{#if typeLabel}
			<span class="type-tag">{typeLabel}</span>
		{/if}
		{#if title.platforms.length > 0}
			<span class="platform-tag">{title.platforms[0]}</span>
		{/if}
	</div>

	<div class="card-info">
		<p class="card-title">{title.title}</p>
		{#if genreLine}
			<p class="card-genres">{genreLine}</p>
		{/if}
		<div class="card-meta">
			{#if title.rating !== null}
				<span class="card-rating">{title.rating} %</span>
			{/if}
			{#if title.year}
				<span class="card-year">{title.year}</span>
			{/if}
		</div>
	</div>
{/snippet}

{#if onclick}
	<button class="poster-card" type="button" onclick={handleClick}>
		{@render cardBody()}
	</button>
{:else}
	<a href="{base}/titul/{title.id}/{title.slug}" class="poster-card">
		{@render cardBody()}
	</a>
{/if}

<style>
	button.poster-card {
		background: none;
		border: none;
		text-align: left;
		width: 100%;
	}

	.poster-media {
		position: relative;
	}

	/* Categorical badges live on the poster; descriptive text lives below it */
	.type-tag {
		position: absolute;
		top: 0.5rem;
		left: 0.5rem;
		font-size: 0.63rem;
		font-weight: 700;
		letter-spacing: 0.04em;
		text-transform: uppercase;
		padding: 3px 7px;
		border-radius: var(--radius-sm);
		background: rgba(8, 14, 30, 0.82);
		color: var(--amber);
		backdrop-filter: blur(4px);
		border: 1px solid var(--border);
	}

	.platform-tag {
		position: absolute;
		bottom: 0.5rem;
		right: 0.5rem;
		max-width: calc(100% - 1rem);
		font-size: 0.63rem;
		font-weight: 600;
		padding: 3px 7px;
		border-radius: var(--radius-sm);
		background: rgba(8, 14, 30, 0.82);
		color: var(--text-primary);
		backdrop-filter: blur(4px);
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}

	.card-genres {
		font-size: 0.72rem;
		color: var(--text-secondary);
		margin-top: 0.2rem;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}
</style>

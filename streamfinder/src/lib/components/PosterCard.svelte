<script lang="ts">
	import type { TitleIndex } from '$lib/types';
	import { base } from '$app/paths';
	import { platformColor } from '$lib/platforms';

	let {
		title,
		onclick,
		serialTitle
	}: {
		title: TitleIndex;
		onclick?: (t: TitleIndex) => void;
		/** In the Kalendár, the name of the serial this release belongs to. */
		serialTitle?: string;
	} = $props();

	// title_type is already a display label (film, seriál, pořad, tv film…) — shown as
	// a badge on every card.
	let typeLabel = $derived(title.title_type ?? null);

	// A release event (episode / season) rather than a top-level work.
	let isChild = $derived(
		title.is_toplevel === false && (title.season_no != null || title.episode_no != null)
	);

	// Episode titles carry a "(S02E05)" marker — strip it for display.
	let cleanTitle = $derived(
		title.title.replace(/\s*\((?:S\d+)?E\d+\)\s*$/i, '').replace(/\s+/g, ' ').trim()
	);

	let seLabel = $derived(
		title.season_no != null && title.episode_no != null
			? `S${title.season_no}·E${title.episode_no}`
			: title.episode_no != null
				? `E${title.episode_no}`
				: title.season_no != null
					? `${title.season_no}. série`
					: null
	);

	let genreLine = $derived(title.genres.slice(0, 2).join(' · '));

	// Kalendár child cards lead with the serial name; catalog cards use their own title.
	let headline = $derived(isChild && serialTitle ? serialTitle : cleanTitle);
	let subLine = $derived.by(() => {
		if (!isChild) return null;
		const bits: string[] = [];
		if (seLabel) bits.push(seLabel);
		if (serialTitle && cleanTitle && cleanTitle !== serialTitle) bits.push(cleanTitle);
		return bits.join(' · ') || null;
	});

	function handleClick() {
		if (onclick) onclick(title);
	}
</script>

{#snippet cardBody()}
	<div class="poster-media">
		{#if title.poster}
			<img src={title.poster} alt={headline} loading="lazy" />
		{:else}
			<div class="poster-placeholder">{headline}</div>
		{/if}

		{#if typeLabel}
			<span class="type-tag">{typeLabel}</span>
		{/if}
		{#if title.is_running}
			<span class="live-tag">beží</span>
		{/if}
		{#if title.platforms.length > 0}
			<span class="platform-tag" style="background: {platformColor(title.platforms[0])}">
				{title.platforms[0]}
			</span>
		{/if}
		{#if isChild && seLabel}
			<span class="se-tag">{seLabel}</span>
		{/if}
	</div>

	<div class="card-info">
		<p class="card-title">{headline}</p>
		{#if subLine}
			<p class="card-sub">{subLine}</p>
		{:else if genreLine}
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
	/* The card is a <button>; keep its layout reset but let the global
	   .poster-card surface (background, border, shadow) show through. */
	button.poster-card {
		font: inherit;
		color: inherit;
		text-align: left;
		width: 100%;
	}

	/* Categorical badges live on the poster; descriptive text lives below it
	   (.poster-media box sizing is defined globally in app.css) */
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

	.live-tag {
		position: absolute;
		top: 0.5rem;
		right: 0.5rem;
		font-size: 0.58rem;
		font-weight: 700;
		letter-spacing: 0.04em;
		text-transform: uppercase;
		padding: 3px 7px;
		border-radius: 999px;
		background: rgba(74, 222, 128, 0.16);
		color: #4ade80;
		border: 1px solid rgba(74, 222, 128, 0.35);
		backdrop-filter: blur(4px);
	}

	.live-tag::before {
		content: '●';
		margin-right: 4px;
		font-size: 0.6em;
		vertical-align: middle;
	}

	.platform-tag,
	.se-tag {
		position: absolute;
		bottom: 0.5rem;
		right: 0.5rem;
		max-width: calc(100% - 1rem);
		z-index: 2;
		font-size: 0.66rem;
		font-weight: 700;
		padding: 3px 8px;
		border-radius: 5px;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}

	/* Platform: solid brand colour (set inline) + edge + lift → legible on any poster */
	.platform-tag {
		color: #fff;
		border: 1px solid rgba(255, 255, 255, 0.18);
		box-shadow: 0 1px 5px rgba(0, 0, 0, 0.4);
		text-shadow: 0 1px 2px rgba(0, 0, 0, 0.35);
	}

	/* Episode marker: neutral dark chip, top-right (leaves the platform its spot).
	   Episodes are never "running", so it never clashes with the live badge. */
	.se-tag {
		top: 0.5rem;
		bottom: auto;
		background: rgba(8, 14, 30, 0.82);
		color: var(--amber);
		font-family: ui-monospace, 'SF Mono', Menlo, monospace;
		backdrop-filter: blur(4px);
	}

	.card-genres,
	.card-sub {
		font-size: 0.72rem;
		margin-top: 0.2rem;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}

	.card-genres {
		color: var(--text-secondary);
	}

	.card-sub {
		color: var(--text-secondary);
	}
</style>

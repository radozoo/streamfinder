<script lang="ts">
	import type { TitleIndex } from '$lib/types';
	import { base } from '$app/paths';

	let { title, onclick }: { title: TitleIndex; onclick?: (t: TitleIndex) => void } = $props();

	function handleClick() {
		if (onclick) onclick(title);
	}
</script>

{#if onclick}
	<button class="poster-card" type="button" onclick={handleClick}>
		{#if title.poster}
			<img src={title.poster} alt={title.title} loading="lazy" />
		{:else}
			<div class="poster-placeholder">{title.title}</div>
		{/if}
		<div class="card-info">
			<p class="card-title">{title.title}</p>
			<div class="card-meta">
				{#if title.rating !== null}
					<span class="card-rating">{title.rating} %</span>
				{/if}
				{#if title.year}
					<span class="card-year">{title.year}</span>
				{/if}
				{#if title.platforms.length > 0}
					<span class="vod-badge">{title.platforms[0]}</span>
				{/if}
			</div>
		</div>
	</button>
{:else}
	<a href="{base}/titul/{title.id}/{title.slug}" class="poster-card">
		{#if title.poster}
			<img src={title.poster} alt={title.title} loading="lazy" />
		{:else}
			<div class="poster-placeholder">{title.title}</div>
		{/if}
		<div class="card-info">
			<p class="card-title">{title.title}</p>
			<div class="card-meta">
				{#if title.rating !== null}
					<span class="card-rating">{title.rating} %</span>
				{/if}
				{#if title.year}
					<span class="card-year">{title.year}</span>
				{/if}
				{#if title.platforms.length > 0}
					<span class="vod-badge">{title.platforms[0]}</span>
				{/if}
			</div>
		</div>
	</a>
{/if}

<style>
	button.poster-card {
		background: none;
		border: none;
		text-align: left;
		width: 100%;
	}
</style>

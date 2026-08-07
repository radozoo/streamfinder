<script lang="ts">
	import type { LayoutData } from './$types';
	import { page } from '$app/state';
	import { base } from '$app/paths';
	import { favorites } from '$lib/favorites.svelte';
	import '../app.css';
	import SearchOverlay from '$lib/components/SearchOverlay.svelte';
	import type { TitleIndex } from '$lib/types';
	import { loadTitles } from '$lib/data/titles';

	let { data, children } = $props();

	let searchOpen = $state(false);

	// Search needs the whole catalog; nothing else in the chrome does. Fetching it on
	// open keeps it off every page view — on the routes that browse the catalog it is
	// already cached, so this costs nothing there either.
	let searchTitles = $state<TitleIndex[] | null>(null);
	async function openSearch() {
		searchOpen = true;
		if (!searchTitles) searchTitles = await loadTitles();
	}

	// The time zone is pinned rather than left to the visitor's machine. Every page
	// here is prerendered, so this string is baked at build time in CI (UTC) and then
	// produced again during hydration in the browser — two different zones would mean
	// two different strings, which is a hydration mismatch and a visible flicker.
	// Europe/Prague is also simply the right zone to read a Czech catalog in.
	const refreshedAt = $derived(
		data.lastRefresh
			? new Date(data.lastRefresh).toLocaleString('cs-CZ', {
					day: 'numeric',
					month: 'long',
					year: 'numeric',
					hour: '2-digit',
					minute: '2-digit',
					timeZone: 'Europe/Prague'
				})
			: null
	);
</script>

<svelte:head>
	<title>Streamfinder</title>
	<meta property="og:site_name" content="Streamfinder" />
	<meta property="og:locale" content="cs_CZ" />
	<meta property="og:type" content="website" />
</svelte:head>

<nav class="nav">
	<a href="{base}/" class="nav-brand">Streamfinder</a>
	<div class="nav-links">
		<a href="{base}/katalog" class:active={page.url.pathname.startsWith(base + '/katalog')}>Katalog</a>
		<a href="{base}/kalendar" class:active={page.url.pathname.startsWith(base + '/kalendar')}>Kalendář</a>
		<a href="{base}/insights" class:active={page.url.pathname.startsWith(base + '/insights')}>Insights</a>
		<a href="{base}/oblibene" class:active={page.url.pathname.startsWith(base + '/oblibene')}>
			Oblíbené{#if favorites.count}<span class="nav-count">{favorites.count}</span>{/if}
		</a>
	</div>
	<button class="nav-search" onclick={openSearch} aria-label="Hledat">
		<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
			<circle cx="11" cy="11" r="8" /><path d="m21 21-4.3-4.3" />
		</svg>
	</button>
</nav>

{#if searchOpen}
	<SearchOverlay titles={searchTitles ?? []} onclose={() => (searchOpen = false)} />
{/if}

<main>
	{@render children()}
</main>

<footer class="footer">
	<div class="footer-inner">
		<span class="footer-brand">Streamfinder</span>
		<span class="footer-sep">&middot;</span>
		<span class="footer-attr">Data z <a href="https://www.csfd.cz" target="_blank" rel="noopener">CSFD.cz</a> &amp; <a href="https://www.themoviedb.org" target="_blank" rel="noopener">TMDB</a></span>
		{#if refreshedAt}
			<span class="footer-sep">&middot;</span>
			<span class="footer-update">
				Data aktualizována <time datetime={data.lastRefresh}>{refreshedAt}</time>
			</span>
		{/if}
	</div>
</footer>

<style>
	.nav {
		position: sticky;
		top: 0;
		z-index: 100;
		display: flex;
		align-items: center;
		gap: 2rem;
		padding: 0 2rem;
		height: 56px;
		background: rgba(8, 14, 30, 0.92);
		backdrop-filter: blur(12px);
		border-bottom: 1px solid rgba(255,255,255,0.06);
	}

	.nav-brand {
		font-family: 'Playfair Display', Georgia, serif;
		font-size: 1.25rem;
		font-weight: 700;
		color: var(--amber);
		text-decoration: none;
		letter-spacing: -0.02em;
	}

	.nav-links {
		display: flex;
		gap: 1.5rem;
	}

	.nav-links a {
		color: var(--text-secondary);
		text-decoration: none;
		font-size: 0.9rem;
		transition: color 0.2s;
	}

	.nav-links a:hover,
	.nav-count {
		margin-left: 0.35rem;
		padding: 1px 6px;
		border-radius: 999px;
		font-size: 0.68rem;
		font-weight: 700;
		background: rgba(244, 63, 94, 0.16);
		color: #fb7185;
		font-variant-numeric: tabular-nums;
	}

	.nav-links a.active {
		color: var(--text-primary);
	}

	.nav-links a.active {
		color: var(--amber);
	}

	main {
		min-height: calc(100vh - 56px - 60px);
	}

	/* Search icon */
	.nav-search {
		margin-left: auto;
		display: flex;
		align-items: center;
		justify-content: center;
		padding: 0.4rem;
		background: none;
		border: none;
		border-radius: 8px;
		color: var(--text-muted);
		cursor: pointer;
		transition: color 0.2s, background 0.2s;
		-webkit-appearance: none;
		appearance: none;
	}

	.nav-search:hover {
		color: var(--amber);
		background: rgba(255, 255, 255, 0.06);
	}

	.nav-search:focus-visible {
		outline: 2px solid var(--amber);
		outline-offset: 2px;
	}

	/* Footer */
	.footer {
		border-top: 1px solid var(--border);
		background: rgba(8, 14, 30, 0.6);
		padding: 1.25rem 2rem;
	}

	.footer-inner {
		max-width: 1400px;
		margin: 0 auto;
		display: flex;
		align-items: center;
		gap: 0.5rem;
		flex-wrap: wrap;
		font-size: 0.78rem;
		color: var(--text-muted);
	}

	.footer-brand {
		font-family: 'Playfair Display', Georgia, serif;
		font-weight: 700;
		color: var(--text-secondary);
	}

	.footer-attr a {
		color: var(--text-secondary);
		text-decoration: underline;
		text-underline-offset: 2px;
	}

	.footer-attr a:hover {
		color: var(--amber);
	}
</style>

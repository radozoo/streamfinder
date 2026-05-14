<script lang="ts">
	import type { LayoutData } from './$types';
	import { page } from '$app/state';
	import { base } from '$app/paths';
	import '../app.css';
	import SearchOverlay from '$lib/components/SearchOverlay.svelte';

	let { data, children } = $props();

	let searchOpen = $state(false);
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
	</div>
	<button class="nav-search" onclick={() => (searchOpen = true)} aria-label="Hledat">
		<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
			<circle cx="11" cy="11" r="8" /><path d="m21 21-4.3-4.3" />
		</svg>
	</button>
</nav>

{#if searchOpen}
	<SearchOverlay titles={data.titles} onclose={() => (searchOpen = false)} />
{/if}

<main>
	{@render children()}
</main>

<footer class="footer">
	<div class="footer-inner">
		<span class="footer-brand">Streamfinder</span>
		<span class="footer-sep">&middot;</span>
		<span class="footer-attr">Data z <a href="https://www.csfd.cz" target="_blank" rel="noopener">CSFD.cz</a> &amp; <a href="https://www.themoviedb.org" target="_blank" rel="noopener">TMDB</a></span>
		{#if data.lastUpdate}
			<span class="footer-sep">&middot;</span>
			<span class="footer-update">Poslední aktualizace: {new Date(data.lastUpdate).toLocaleDateString('cs-CZ', { day: 'numeric', month: 'long', year: 'numeric' })}</span>
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
		color: var(--text-secondary);
		transition: color 0.2s;
		display: flex;
		align-items: center;
	}

	.nav-search:hover {
		color: var(--amber);
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

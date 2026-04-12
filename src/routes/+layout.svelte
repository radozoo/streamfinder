<script lang="ts">
	import type { LayoutData } from './$types';
	import { page } from '$app/state';
	import { base } from '$app/paths';
	import '../app.css';

	let { data, children } = $props();
</script>

<svelte:head>
	<title>Streamfinder</title>
</svelte:head>

<nav class="nav">
	<a href="{base}/" class="nav-brand">Streamfinder</a>
	<div class="nav-links">
		<a href="{base}/katalog" class:active={page.url.pathname.startsWith(base + '/katalog')}>Katalog</a>
		<a href="{base}/kalendar" class:active={page.url.pathname.startsWith(base + '/kalendar')}>Kalendář</a>
		<a href="{base}/insights" class:active={page.url.pathname.startsWith(base + '/insights')}>Insights</a>
	</div>
</nav>

<main>
	{@render children()}
</main>

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
		font-family: 'Georgia', serif;
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
		min-height: calc(100vh - 56px);
	}
</style>

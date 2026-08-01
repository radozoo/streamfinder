<script lang="ts">
	import type { PageData } from './$types';
	import type { TitleIndex } from '$lib/types';
	import PosterCard from '$lib/components/PosterCard.svelte';
	import { favorites } from '$lib/favorites.svelte';
	import { base } from '$app/paths';

	let { data }: { data: PageData } = $props();

	// csfd_id → title, built once. Favourites are stored as ids, so the page is a
	// lookup: whatever is in the list and still in the catalog gets rendered.
	let byCsfdId = $derived(
		new Map(data.titles.filter((t) => t.csfd_id != null).map((t) => [t.csfd_id as number, t]))
	);

	let items = $derived(
		favorites.ids.map((id) => byCsfdId.get(id)).filter((t): t is TitleIndex => Boolean(t))
	);

	// A saved id with no title behind it — the title left the catalog, or the list came
	// from an import made against a newer export. Counted rather than hidden, so the
	// number on screen always adds up to what is actually stored.
	let missing = $derived(favorites.count - items.length);

	let importError = $state<string | null>(null);
	let importNote = $state<string | null>(null);
	let fileInput = $state<HTMLInputElement | null>(null);

	function download() {
		const blob = new Blob([favorites.exportJson()], { type: 'application/json' });
		const url = URL.createObjectURL(blob);
		const a = document.createElement('a');
		a.href = url;
		a.download = `streamfinder-oblibene-${new Date().toISOString().slice(0, 10)}.json`;
		a.click();
		URL.revokeObjectURL(url);
	}

	async function onFile(e: Event) {
		const file = (e.target as HTMLInputElement).files?.[0];
		if (!file) return;
		importError = null;
		importNote = null;
		try {
			const { added, total } = favorites.importJson(await file.text());
			importNote = added
				? `Přidáno ${added} titulů, celkem ${total}.`
				: `Nic nového — všech ${total} titulů už v seznamu bylo.`;
		} catch (err) {
			importError = err instanceof Error ? err.message : 'Soubor se nepodařilo načíst';
		} finally {
			if (fileInput) fileInput.value = '';
		}
	}
</script>

<svelte:head>
	<title>Oblíbené — Streamfinder</title>
	<meta name="robots" content="noindex" />
</svelte:head>

<div class="page-container">
	<div class="fav-header">
		<div>
			<h1 class="section-title">Oblíbené</h1>
			<p class="fav-sub">
				{#if favorites.count === 0}
					Zatím prázdné — klepnutím na srdíčko u titulu si sem cokoliv uložíte.
				{:else}
					{favorites.count}
					{favorites.count === 1 ? 'titul' : favorites.count < 5 ? 'tituly' : 'titulů'}
					· uloženo jen v tomto prohlížeči
				{/if}
			</p>
		</div>

		{#if favorites.count > 0}
			<div class="fav-actions">
				<button class="fav-tool" type="button" onclick={download}>Stáhnout zálohu</button>
				<button class="fav-tool" type="button" onclick={() => fileInput?.click()}>Načíst ze zálohy</button>
			</div>
		{/if}
	</div>

	<!-- Kept out of the conditional above so importing works from the empty state too. -->
	<input
		bind:this={fileInput}
		type="file"
		accept="application/json,.json"
		class="visually-hidden"
		onchange={onFile}
	/>

	{#if importNote}<p class="fav-note">{importNote}</p>{/if}
	{#if importError}<p class="fav-note error">{importError}</p>{/if}

	{#if items.length}
		<div class="fav-grid">
			{#each items as title (title.id)}
				<PosterCard {title} />
			{/each}
		</div>

		{#if missing > 0}
			<p class="fav-note">
				{missing}
				{missing === 1 ? 'uložený titul už není' : 'uložené tituly už nejsou'} v katalogu.
			</p>
		{/if}
	{:else}
		<div class="fav-empty">
			<p>Nic tu zatím není.</p>
			<p class="fav-empty-hint">
				Srdíčko najdete v rohu každé karty i na stránce titulu. Seznam zůstává v tomto
				prohlížeči — nikam se neodesílá.
			</p>
			<div class="fav-empty-actions">
				<a class="fav-cta" href="{base}/katalog">Procházet katalog</a>
				<button class="fav-tool" type="button" onclick={() => fileInput?.click()}>
					Načíst ze zálohy
				</button>
			</div>
		</div>
	{/if}
</div>

<style>
	.fav-header {
		display: flex;
		flex-wrap: wrap;
		align-items: flex-end;
		justify-content: space-between;
		gap: 1rem;
		margin-bottom: 1.5rem;
	}

	.fav-sub {
		margin-top: 0.35rem;
		font-size: 0.85rem;
		color: var(--text-secondary);
	}

	.fav-actions {
		display: flex;
		gap: 0.5rem;
	}

	.fav-tool {
		font: inherit;
		font-size: 0.8rem;
		padding: 0.45rem 0.85rem;
		border-radius: var(--radius-sm);
		background: var(--navy-700);
		border: 1px solid var(--border);
		color: var(--text-secondary);
		cursor: pointer;
	}

	.fav-tool:hover {
		color: var(--text-primary);
		border-color: var(--navy-500);
	}

	.fav-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
		gap: 1rem;
	}

	@media (max-width: 640px) {
		.fav-grid {
			grid-template-columns: repeat(auto-fill, minmax(130px, 1fr));
		}
	}

	.fav-note {
		margin-top: 1rem;
		font-size: 0.8rem;
		color: var(--text-secondary);
	}

	.fav-note.error {
		color: #fb7185;
	}

	.fav-empty {
		padding: 3rem 1rem;
		text-align: center;
		border: 1px dashed var(--border);
		border-radius: var(--radius);
	}

	.fav-empty-hint {
		max-width: 34rem;
		margin: 0.5rem auto 0;
		font-size: 0.85rem;
		color: var(--text-secondary);
	}

	.fav-empty-actions {
		display: flex;
		gap: 0.6rem;
		justify-content: center;
		flex-wrap: wrap;
		margin-top: 1.25rem;
	}

	.fav-cta {
		font-size: 0.85rem;
		font-weight: 600;
		padding: 0.5rem 1rem;
		border-radius: var(--radius-sm);
		background: var(--amber);
		color: var(--navy-900);
	}

	.visually-hidden {
		position: absolute;
		width: 1px;
		height: 1px;
		overflow: hidden;
		clip: rect(0 0 0 0);
		white-space: nowrap;
	}
</style>

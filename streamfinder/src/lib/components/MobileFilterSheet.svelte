<!--
	The filter affordance for narrow screens: a floating button and the bottom sheet
	it opens.

	`FilterBar` is a row of dropdowns that does not fit a phone, so it is
	`display: none` under 640px. Katalog paired that with this sheet; Kalendář never
	got one, which left its filters unreachable on a phone — the bar was hidden and
	nothing replaced it. Lifting the sheet out of Katalog is what makes it available
	to both, rather than copying 300 lines and letting the two drift.

	The prop names deliberately match FilterBar's, so a page wires up the same values
	twice with the same words and a reader can see they are the same filters in two
	layouts. Open state is owned here: no page has a reason to control it.
-->
<script lang="ts">
	import type { CrewEntry } from '$lib/types';
	import PillGrid from './PillGrid.svelte';
	import AutocompleteDropdown from './AutocompleteDropdown.svelte';
	import RangeSlider from './RangeSlider.svelte';

	let {
		genres,
		platforms,
		countries,
		tags,
		tagsTop = undefined,
		typeOptions,
		crewItems = [],
		crewLoading = false,
		crewLoaded = false,
		onLoadCrew,
		onTagsEngage = undefined,
		tagsLoading = false,
		selectedGenres,
		selectedPlatforms,
		selectedCountries,
		selectedTags,
		selectedTypes,
		selectedCrew,
		yearFrom,
		yearTo,
		ratingMin,
		yearMin = 1920,
		yearMax = 2026,
		// Optional: Kalendář has no "added to VOD" window — its whole axis is the date.
		recencyOptions = undefined,
		recencyDays = 0,
		onRecencyChange = undefined,
		onToggleGenre,
		onTogglePlatform,
		onToggleCountry,
		onToggleTag,
		onToggleType,
		onSelectCrew,
		onRemoveCrew,
		onYearChange,
		onRatingChange,
		// Sheet chrome
		activeFilterCount = 0,
		hasFilters = false,
		onClearAll,
		resultCount = 0
	}: {
		genres: { name: string; count: number; hit: boolean }[];
		platforms: { name: string; count: number; hit: boolean }[];
		countries: { name: string; count: number; hit: boolean }[];
		tags: { name: string; count: number }[];
		tagsTop?: { name: string; count: number; hit: boolean }[];
		typeOptions: string[];
		crewItems?: CrewEntry[];
		crewLoading?: boolean;
		crewLoaded?: boolean;
		onLoadCrew: () => void;
		onTagsEngage?: () => void;
		tagsLoading?: boolean;
		selectedGenres: string[];
		selectedPlatforms: string[];
		selectedCountries: string[];
		selectedTags: string[];
		selectedTypes: string[];
		selectedCrew: string[];
		yearFrom: number;
		yearTo: number;
		ratingMin: number;
		yearMin?: number;
		yearMax?: number;
		recencyOptions?: { label: string; days: number }[];
		recencyDays?: number;
		onRecencyChange?: (days: number) => void;
		onToggleGenre: (name: string) => void;
		onTogglePlatform: (name: string) => void;
		onToggleCountry: (name: string) => void;
		onToggleTag: (name: string) => void;
		onToggleType: (name: string) => void;
		onSelectCrew: (name: string) => void;
		onRemoveCrew: (name: string) => void;
		onYearChange: (from: number, to: number) => void;
		onRatingChange: (from: number, to: number) => void;
		activeFilterCount?: number;
		hasFilters?: boolean;
		onClearAll: () => void;
		resultCount?: number;
	} = $props();

	let open = $state(false);

	let typeItems = $derived(typeOptions.map((t) => ({ name: t, hit: true })));

	// Escape closes it. Handled on the window rather than the backdrop, because the
	// backdrop only receives key events while it holds focus — which it does not after
	// the visitor has tapped a pill inside the sheet.
	function onKeydown(e: KeyboardEvent) {
		if (e.key === 'Escape') open = false;
	}
</script>

<svelte:window onkeydown={onKeydown} />

<button class="filter-fab" onclick={() => (open = true)} aria-label="Otevřít filtry">
	<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
		<line x1="4" y1="6" x2="20" y2="6" />
		<line x1="8" y1="12" x2="20" y2="12" />
		<line x1="12" y1="18" x2="20" y2="18" />
	</svg>
	Filtrovat
	{#if activeFilterCount > 0}
		<span class="fab-badge">{activeFilterCount}</span>
	{/if}
</button>

{#if open}
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div
		class="sheet-backdrop"
		onclick={(e) => {
			// Close only when the backdrop itself was hit. The alternative — closing on
			// any click and stopping propagation inside the sheet — needs a click handler
			// on the sheet, which is not an interactive control and should not have one.
			if (e.target === e.currentTarget) open = false;
		}}
		onkeydown={(e) => e.key === 'Escape' && (open = false)}
		role="presentation"
		tabindex="-1"
	>
		<div
			class="filter-sheet"
			role="dialog"
			aria-modal="true"
			aria-label="Filtry"
			tabindex="-1"
		>
			<div class="sheet-header">
				<h2 class="sheet-title">Filtry</h2>
				{#if hasFilters}
					<button class="clear-btn" onclick={onClearAll}>Zrušit filtry</button>
				{/if}
				<button class="sheet-close" onclick={() => (open = false)} aria-label="Zavřít">&#x2715;</button>
			</div>

			<div class="sheet-body">
				{#if recencyOptions && onRecencyChange}
					<div class="filter-group">
						<h3 class="filter-label">Přidáno na VOD</h3>
						<div class="recency-seg" role="radiogroup" aria-label="Přidáno na VOD">
							{#each recencyOptions as opt}
								<button
									type="button"
									class="recency-opt"
									class:active={recencyDays === opt.days}
									role="radio"
									aria-checked={recencyDays === opt.days}
									onclick={() => onRecencyChange?.(opt.days)}
								>
									{opt.label}
								</button>
							{/each}
						</div>
					</div>
				{/if}

				<div class="filter-group">
					<h3 class="filter-label">Typ</h3>
					<PillGrid items={typeItems} selected={selectedTypes} onToggle={onToggleType} />
				</div>

				<div class="filter-group">
					<h3 class="filter-label">Platforma</h3>
					<PillGrid items={platforms.slice(0, 12)} selected={selectedPlatforms} onToggle={onTogglePlatform} />
				</div>

				<div class="filter-group">
					<h3 class="filter-label">Žánr</h3>
					<PillGrid items={genres.slice(0, 20)} selected={selectedGenres} onToggle={onToggleGenre} />
				</div>

				{#if countries.length > 0}
					<div class="filter-group">
						<h3 class="filter-label">Země</h3>
						<PillGrid items={countries} selected={selectedCountries} onToggle={onToggleCountry} />
					</div>
				{/if}

				<div class="filter-group">
					<h3 class="filter-label">Tagy</h3>
					<AutocompleteDropdown
						items={tags}
						topItems={tagsTop}
						topLabel="Nejčastější tagy"
						selected={selectedTags}
						onSelect={onToggleTag}
						onRemove={onToggleTag}
						placeholder="Hledat tagy…"
						loading={tagsLoading}
						onEngage={onTagsEngage}
					/>
				</div>

				<div class="filter-group">
					<h3 class="filter-label">Tvůrci</h3>
					{#if !crewLoaded}
						<button class="load-crew-btn" onclick={onLoadCrew}>
							{crewLoading ? 'Načítání…' : 'Načíst tvůrce'}
						</button>
					{:else}
						<AutocompleteDropdown
							items={crewItems}
							selected={selectedCrew}
							onSelect={onSelectCrew}
							onRemove={onRemoveCrew}
							placeholder="Hledat herce, režiséry…"
							formatItem={(item) => `${item.name} (${item.role ?? ''}, ${item.count ?? ''})`}
						/>
					{/if}
				</div>

				<div class="filter-group">
					<h3 class="filter-label">Rok výroby</h3>
					<RangeSlider
						min={yearMin}
						max={yearMax}
						step={1}
						valueFrom={yearFrom}
						valueTo={yearTo}
						onChange={onYearChange}
					/>
				</div>

				<div class="filter-group">
					<h3 class="filter-label">Min. hodnocení</h3>
					<RangeSlider
						min={0}
						max={100}
						step={5}
						valueFrom={ratingMin}
						valueTo={100}
						onChange={onRatingChange}
						single
						suffix="%"
					/>
				</div>
			</div>

			<div class="sheet-footer">
				<button class="apply-btn" onclick={() => (open = false)}>
					Zobrazit {resultCount.toLocaleString('cs-CZ')} titulů
				</button>
			</div>
		</div>
	</div>
{/if}

<style>
	/* Recency segmented control */
	.recency-seg {
		display: inline-flex;
		flex-wrap: wrap;
		gap: 2px;
		padding: 3px;
		background: var(--navy-700);
		border: 1px solid var(--border);
		border-radius: 999px;
	}

	.recency-opt {
		padding: 0.35rem 0.85rem;
		border: none;
		background: none;
		border-radius: 999px;
		color: var(--text-secondary);
		font-size: 0.82rem;
		font-weight: 600;
		cursor: pointer;
		white-space: nowrap;
		transition: background 0.15s, color 0.15s;
	}

	.recency-opt:hover {
		color: var(--text-primary);
	}

	.recency-opt.active {
		background: var(--amber);
		color: var(--navy-900);
	}

	.recency-opt:focus-visible {
		outline: 2px solid var(--amber);
		outline-offset: 2px;
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

	.load-crew-btn {
		background: var(--navy-700);
		border: 1px solid var(--border);
		border-radius: var(--radius-sm);
		padding: 0.5rem 1rem;
		color: var(--text-secondary);
		font-size: 0.82rem;
		cursor: pointer;
	}

	.clear-btn {
		background: none;
		border: 1px solid var(--border);
		border-radius: var(--radius-sm);
		padding: 0.35rem 0.75rem;
		color: var(--text-secondary);
		font-size: 0.8rem;
		cursor: pointer;
	}

	/* Mobile FAB */
	.filter-fab {
		display: none;
		position: fixed;
		bottom: 1.5rem;
		left: 50%;
		transform: translateX(-50%);
		z-index: 50;
		background: var(--amber);
		color: var(--navy-900);
		border: none;
		border-radius: 999px;
		padding: 0.65rem 1.5rem;
		font-size: 0.9rem;
		font-weight: 700;
		cursor: pointer;
		gap: 0.4rem;
		align-items: center;
		box-shadow: 0 4px 20px rgba(0, 0, 0, 0.4);
	}

	.fab-badge {
		background: var(--navy-900);
		color: var(--amber);
		border-radius: 999px;
		width: 20px;
		height: 20px;
		font-size: 0.7rem;
		font-weight: 800;
		display: flex;
		align-items: center;
		justify-content: center;
	}

	/* Mobile bottom sheet */
	.sheet-backdrop {
		position: fixed;
		inset: 0;
		background: rgba(0, 0, 0, 0.6);
		z-index: 150;
		display: flex;
		align-items: flex-end;
	}

	.filter-sheet {
		width: 100%;
		background: var(--navy-800);
		border-radius: var(--radius) var(--radius) 0 0;
		border-top: 1px solid var(--border);
		max-height: 85vh;
		display: flex;
		flex-direction: column;
	}

	.sheet-header {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		padding: 1rem 1.25rem;
		border-bottom: 1px solid var(--border);
		flex-shrink: 0;
	}

	.sheet-title {
		font-family: 'Playfair Display', Georgia, serif;
		font-size: 1.1rem;
		font-weight: 700;
		flex: 1;
	}

	.sheet-close {
		background: none;
		border: none;
		color: var(--text-muted);
		font-size: 1rem;
		cursor: pointer;
		padding: 0.25rem;
	}

	.sheet-body {
		overflow-y: auto;
		padding: 1.25rem;
		display: flex;
		flex-direction: column;
		gap: 1.25rem;
		flex: 1;
	}

	.sheet-footer {
		padding: 1rem 1.25rem;
		border-top: 1px solid var(--border);
		flex-shrink: 0;
	}

	.apply-btn {
		width: 100%;
		background: var(--amber);
		color: var(--navy-900);
		border: none;
		border-radius: var(--radius);
		padding: 0.75rem;
		font-size: 0.95rem;
		font-weight: 700;
		cursor: pointer;
		transition: opacity 0.15s;
	}

	.apply-btn:hover {
		opacity: 0.9;
	}

	@media (max-width: 640px) {
		.filter-fab {
			display: flex;
		}
	}
</style>

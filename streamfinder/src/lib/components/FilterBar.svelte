<script lang="ts">
	import type { CrewEntry } from '$lib/types';
	import FilterDropdown from './FilterDropdown.svelte';
	import PillGrid from './PillGrid.svelte';
	import AutocompleteDropdown from './AutocompleteDropdown.svelte';
	import RangeSlider from './RangeSlider.svelte';

	let {
		// Pill dimensions (with hit indicator)
		genres,
		platforms,
		countries,
		tags,
		tagsTop = undefined,
		typeOptions,
		// Crew (lazy-loaded)
		crewItems = [],
		crewLoading = false,
		onCrewHover,
		onTagsEngage = undefined,
		tagsLoading = false,
		// Selected state
		selectedGenres,
		selectedPlatforms,
		selectedCountries,
		selectedTags,
		selectedTypes,
		favoritesOnly = false,
		favoritesCount = 0,
		selectedCrew,
		yearFrom,
		yearTo,
		ratingMin,
		yearMin = 1920,
		yearMax = 2026,
		// Recency ("Přidáno na VOD") — optional; the dropdown only renders when provided
		recencyOptions = undefined,
		recencyDays = 0,
		onRecencyChange = undefined,
		// Callbacks
		onToggleGenre,
		onTogglePlatform,
		onToggleCountry,
		onToggleTag,
		onToggleType,
		onToggleFavoritesOnly,
		onSelectCrew,
		onRemoveCrew,
		onYearChange,
		onRatingChange,
	}: {
		genres: { name: string; count: number; hit: boolean }[];
		platforms: { name: string; count: number; hit: boolean }[];
		countries: { name: string; count: number; hit: boolean }[];
		tags: { name: string; count: number }[];
		tagsTop?: { name: string; count: number; hit: boolean }[];
		typeOptions: string[];
		crewItems?: CrewEntry[];
		crewLoading?: boolean;
		onCrewHover?: () => void;
		// Same deal as crew: the full tag list is fetched on demand.
		onTagsEngage?: () => void;
		tagsLoading?: boolean;
		selectedGenres: string[];
		selectedPlatforms: string[];
		selectedCountries: string[];
		selectedTags: string[];
		selectedTypes: string[];
		favoritesOnly?: boolean;
		favoritesCount?: number;
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
		onToggleFavoritesOnly?: () => void;
		onSelectCrew: (name: string) => void;
		onRemoveCrew: (name: string) => void;
		onYearChange: (from: number, to: number) => void;
		onRatingChange: (from: number, to: number) => void;
	} = $props();

	let typeItems = $derived(
		typeOptions.map((t) => ({ name: t, hit: true }))
	);

	let recencyLabel = $derived(
		recencyDays > 0
			? 'Přidáno · ' + (recencyOptions?.find((o) => o.days === recencyDays)?.label ?? '')
			: 'Přidáno'
	);

	function formatCrew(item: { name: string; role?: string; count?: number }) {
		const parts = [item.name];
		if (item.role) parts.push(`(${item.role}`);
		if (item.count !== undefined && item.role) parts[parts.length - 1] += `, ${item.count}`;
		if (item.role) parts[parts.length - 1] += ')';
		return parts.join(' ');
	}
</script>

<div class="filter-bar">
	{#if recencyOptions && onRecencyChange}
		<FilterDropdown label={recencyLabel} activeCount={recencyDays > 0 ? 1 : 0}>
			<div class="recency-list" role="radiogroup" aria-label="Přidáno na VOD">
				{#each recencyOptions as opt}
					<button
						type="button"
						class="recency-item"
						class:active={recencyDays === opt.days}
						role="radio"
						aria-checked={recencyDays === opt.days}
						onclick={() => onRecencyChange(opt.days)}
					>
						<span>{opt.label}</span>
						{#if recencyDays === opt.days}
							<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
						{/if}
					</button>
				{/each}
			</div>
		</FilterDropdown>
	{/if}

	{#if onToggleFavoritesOnly}
		<!-- A switch, not a dropdown: there is nothing to choose inside it. Hidden until
		     something is actually favourited, so it never offers an empty result. -->
		<button
			class="fav-filter"
			class:on={favoritesOnly}
			type="button"
			aria-pressed={favoritesOnly}
			disabled={favoritesCount === 0}
			title={favoritesCount === 0 ? 'Zatím nemáte žádné oblíbené' : 'Zobrazit jen oblíbené'}
			onclick={onToggleFavoritesOnly}
		>
			<svg viewBox="0 0 24 24" aria-hidden="true" width="14" height="14">
				<path d="M12 20s-7-4.4-9.5-9C.5 7.3 2.7 4 6 4c2 0 3.4 1 4 2.2C10.6 5 12 4 14 4c3.3 0 5.5 3.3 3.5 7-2.5 4.6-9.5 9-9.5 9z" />
			</svg>
			Oblíbené
			{#if favoritesCount}<span class="fav-filter-count">{favoritesCount}</span>{/if}
		</button>
	{/if}

	<FilterDropdown label="Žánr" activeCount={selectedGenres.length}>
		<PillGrid items={genres} selected={selectedGenres} onToggle={onToggleGenre} />
	</FilterDropdown>

	<FilterDropdown label="Platforma" activeCount={selectedPlatforms.length}>
		<PillGrid items={platforms} selected={selectedPlatforms} onToggle={onTogglePlatform} />
	</FilterDropdown>

	<FilterDropdown label="Krajina" activeCount={selectedCountries.length}>
		<PillGrid items={countries} selected={selectedCountries} onToggle={onToggleCountry} />
	</FilterDropdown>

	<FilterDropdown label="Typ" activeCount={selectedTypes.length}>
		<PillGrid items={typeItems} selected={selectedTypes} onToggle={onToggleType} />
	</FilterDropdown>

	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div onmouseenter={onTagsEngage}>
		<FilterDropdown label="Tagy" activeCount={selectedTags.length}>
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
		</FilterDropdown>
	</div>

	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div onmouseenter={onCrewHover}>
		<FilterDropdown label="Tvůrci" activeCount={selectedCrew.length}>
			<AutocompleteDropdown
				items={crewItems}
				selected={selectedCrew}
				onSelect={onSelectCrew}
				onRemove={onRemoveCrew}
				placeholder="Hledat herce, režiséry…"
				formatItem={formatCrew}
				loading={crewLoading}
			/>
		</FilterDropdown>
	</div>

	<FilterDropdown label="Rok" activeCount={yearFrom > yearMin || yearTo < yearMax ? 1 : 0}>
		<RangeSlider
			min={yearMin}
			max={yearMax}
			step={1}
			valueFrom={yearFrom}
			valueTo={yearTo}
			onChange={onYearChange}
		/>
	</FilterDropdown>

	<FilterDropdown label="Hodnocení" activeCount={ratingMin > 0 ? 1 : 0}>
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
	</FilterDropdown>
</div>

<style>
	.fav-filter {
		display: inline-flex;
		align-items: center;
		gap: 0.35rem;
		flex-shrink: 0;
		font: inherit;
		font-size: 0.82rem;
		padding: 0.45rem 0.8rem;
		border-radius: var(--radius-sm);
		background: var(--navy-700);
		border: 1px solid var(--border);
		color: var(--text-secondary);
		cursor: pointer;
	}

	.fav-filter svg {
		fill: none;
		stroke: currentColor;
		stroke-width: 1.8;
		stroke-linejoin: round;
	}

	.fav-filter:hover:not(:disabled) {
		color: var(--text-primary);
	}

	.fav-filter.on {
		color: #fb7185;
		border-color: rgba(244, 63, 94, 0.4);
		background: rgba(244, 63, 94, 0.1);
	}

	.fav-filter.on svg {
		fill: #f43f5e;
	}

	.fav-filter:disabled {
		opacity: 0.45;
		cursor: not-allowed;
	}

	.fav-filter-count {
		font-variant-numeric: tabular-nums;
		font-weight: 700;
	}

	.filter-bar {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		overflow-x: auto;
		padding-bottom: 0.25rem;
		scrollbar-width: thin;
		scrollbar-color: var(--navy-600) transparent;
	}

	.filter-bar::-webkit-scrollbar {
		height: 4px;
	}

	.filter-bar::-webkit-scrollbar-thumb {
		background: var(--navy-600);
		border-radius: 2px;
	}

	/* Single-select recency list inside its dropdown */
	.recency-list {
		display: flex;
		flex-direction: column;
		gap: 2px;
		min-width: 160px;
	}

	.recency-item {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.75rem;
		padding: 0.5rem 0.7rem;
		border: none;
		background: none;
		border-radius: 8px;
		color: var(--text-secondary);
		font-size: 0.88rem;
		text-align: left;
		cursor: pointer;
		transition: background 0.15s, color 0.15s;
	}

	.recency-item:hover {
		background: var(--navy-700);
		color: var(--text-primary);
	}

	.recency-item.active {
		color: var(--amber);
		font-weight: 700;
	}

	.recency-item:focus-visible {
		outline: 2px solid var(--amber);
		outline-offset: -2px;
	}

	@media (max-width: 640px) {
		.filter-bar {
			display: none;
		}
	}
</style>

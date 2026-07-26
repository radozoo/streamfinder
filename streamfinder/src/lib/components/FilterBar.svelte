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
		typeOptions,
		// Crew (lazy-loaded)
		crewItems = [],
		crewLoading = false,
		onCrewHover,
		// Selected state
		selectedGenres,
		selectedPlatforms,
		selectedCountries,
		selectedTags,
		selectedType,
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
		onSelectCrew,
		onRemoveCrew,
		onYearChange,
		onRatingChange,
	}: {
		genres: { name: string; count: number; hit: boolean }[];
		platforms: { name: string; count: number; hit: boolean }[];
		countries: { name: string; count: number; hit: boolean }[];
		tags: { name: string; count: number; hit: boolean }[];
		typeOptions: string[];
		crewItems?: CrewEntry[];
		crewLoading?: boolean;
		onCrewHover?: () => void;
		selectedGenres: string[];
		selectedPlatforms: string[];
		selectedCountries: string[];
		selectedTags: string[];
		selectedType: string;
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

	<FilterDropdown label="Žánr" activeCount={selectedGenres.length}>
		<PillGrid items={genres} selected={selectedGenres} onToggle={onToggleGenre} />
	</FilterDropdown>

	<FilterDropdown label="Platforma" activeCount={selectedPlatforms.length}>
		<PillGrid items={platforms} selected={selectedPlatforms} onToggle={onTogglePlatform} />
	</FilterDropdown>

	<FilterDropdown label="Krajina" activeCount={selectedCountries.length}>
		<PillGrid items={countries} selected={selectedCountries} onToggle={onToggleCountry} />
	</FilterDropdown>

	<FilterDropdown label="Typ" activeCount={selectedType ? 1 : 0}>
		<PillGrid items={typeItems} selected={selectedType ? [selectedType] : []} onToggle={onToggleType} />
	</FilterDropdown>

	<FilterDropdown label="Tagy" activeCount={selectedTags.length}>
		<AutocompleteDropdown
			items={tags}
			selected={selectedTags}
			onSelect={onToggleTag}
			onRemove={onToggleTag}
			placeholder="Hledat tagy…"
		/>
	</FilterDropdown>

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

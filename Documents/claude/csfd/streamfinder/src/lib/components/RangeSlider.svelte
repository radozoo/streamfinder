<script lang="ts">
	let {
		min = 0,
		max = 100,
		step = 1,
		valueFrom,
		valueTo,
		onChange,
		single = false,
		suffix = '',
		label = ''
	}: {
		min?: number;
		max?: number;
		step?: number;
		valueFrom: number;
		valueTo: number;
		onChange: (from: number, to: number) => void;
		single?: boolean;
		suffix?: string;
		label?: string;
	} = $props();

	function handleFromInput(e: Event) {
		const v = Number((e.target as HTMLInputElement).value);
		const from = Math.min(v, valueTo);
		const to = Math.max(v, valueTo);
		onChange(from, to);
	}

	function handleToInput(e: Event) {
		const v = Number((e.target as HTMLInputElement).value);
		const from = Math.min(valueFrom, v);
		const to = Math.max(valueFrom, v);
		onChange(from, to);
	}

	function handleSingleInput(e: Event) {
		const v = Number((e.target as HTMLInputElement).value);
		onChange(v, max);
	}

	let trackPercent = $derived.by(() => {
		const range = max - min || 1;
		if (single) {
			return { left: 0, width: ((valueFrom - min) / range) * 100 };
		}
		const left = ((valueFrom - min) / range) * 100;
		const right = ((valueTo - min) / range) * 100;
		return { left, width: right - left };
	});
</script>

<div class="range-slider">
	{#if label}
		<div class="range-label">{label}</div>
	{/if}

	<div class="range-values">
		{#if single}
			<span class="range-value">{valueFrom}{suffix}+</span>
		{:else}
			<span class="range-value">{valueFrom}{suffix}</span>
			<span class="range-sep">–</span>
			<span class="range-value">{valueTo}{suffix}</span>
		{/if}
	</div>

	<div class="range-track-wrapper">
		<div class="range-track">
			<div
				class="range-fill"
				style="left: {trackPercent.left}%; width: {trackPercent.width}%"
			></div>
		</div>

		{#if single}
			<input
				class="range-input"
				type="range"
				{min}
				{max}
				{step}
				value={valueFrom}
				oninput={handleSingleInput}
			/>
		{:else}
			<input
				class="range-input"
				type="range"
				{min}
				{max}
				{step}
				value={valueFrom}
				oninput={handleFromInput}
			/>
			<input
				class="range-input"
				type="range"
				{min}
				{max}
				{step}
				value={valueTo}
				oninput={handleToInput}
			/>
		{/if}
	</div>
</div>

<style>
	.range-slider {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
		min-width: 200px;
	}

	.range-label {
		font-size: 0.7rem;
		font-weight: 700;
		letter-spacing: 0.08em;
		text-transform: uppercase;
		color: var(--text-muted);
	}

	.range-values {
		display: flex;
		align-items: center;
		gap: 0.3rem;
		justify-content: center;
	}

	.range-value {
		font-size: 0.9rem;
		font-weight: 600;
		color: var(--amber);
	}

	.range-sep {
		color: var(--text-muted);
		font-size: 0.8rem;
	}

	.range-track-wrapper {
		position: relative;
		height: 28px;
		display: flex;
		align-items: center;
	}

	.range-track {
		position: absolute;
		left: 0;
		right: 0;
		height: 4px;
		background: var(--navy-600);
		border-radius: 2px;
	}

	.range-fill {
		position: absolute;
		height: 100%;
		background: var(--amber);
		border-radius: 2px;
	}

	.range-input {
		position: absolute;
		width: 100%;
		height: 100%;
		margin: 0;
		-webkit-appearance: none;
		appearance: none;
		background: transparent;
		pointer-events: none;
		outline: none;
	}

	.range-input::-webkit-slider-thumb {
		-webkit-appearance: none;
		width: 16px;
		height: 16px;
		border-radius: 50%;
		background: var(--amber);
		border: 2px solid var(--navy-800);
		cursor: pointer;
		pointer-events: all;
		position: relative;
		z-index: 2;
	}

	.range-input::-moz-range-thumb {
		width: 16px;
		height: 16px;
		border-radius: 50%;
		background: var(--amber);
		border: 2px solid var(--navy-800);
		cursor: pointer;
		pointer-events: all;
	}
</style>

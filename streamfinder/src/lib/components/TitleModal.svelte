<script lang="ts">
	import type { TitleDetail, EpisodeRelease } from '$lib/types';

	interface Props {
		title: TitleDetail | null;
		loading: boolean;
		onclose: () => void;
		/** Open another title by its id (used by the "jump to serial" link). */
		onopentitle?: (id: number) => void;
	}

	let { title, loading, onclose, onopentitle }: Props = $props();

	const ACTOR_LIMIT = 20;
	let actorsExpanded = $state(false);

	// Reset the "více" toggle whenever a different title opens
	$effect(() => {
		title?.id;
		actorsExpanded = false;
	});

	// Czech plural: 1 → one, 2–4 → few, 5+ → many
	function czPlural(n: number, one: string, few: string, many: string): string {
		if (n === 1) return one;
		if (n >= 2 && n <= 4) return few;
		return many;
	}

	// Serial shape line: "2 série · 18 epizod"
	let shapeText = $derived.by(() => {
		if (!title) return null;
		const parts: string[] = [];
		if (title.season_count && title.season_count > 1) {
			parts.push(`${title.season_count} ${czPlural(title.season_count, 'série', 'série', 'sérií')}`);
		}
		if (title.episode_count) {
			const w: [string, string, string] =
				title.title_type === 'pořad' ? ['díl', 'díly', 'dílů'] : ['epizoda', 'epizody', 'epizod'];
			parts.push(`${title.episode_count} ${czPlural(title.episode_count, w[0], w[1], w[2])}`);
		}
		return parts.join(' · ') || null;
	});

	// ── Release timeline (top-level serials) ──────────────────────────────────
	interface SeasonGroup {
		season: number | null;
		eps: EpisodeRelease[];
		first: string | null;
		last: string | null;
	}

	let seasons = $derived.by((): SeasonGroup[] => {
		const eps = title?.episodes;
		if (!eps || !eps.length) return [];
		const map = new Map<number, EpisodeRelease[]>();
		for (const e of eps) {
			const s = e.season_no ?? 0;
			if (!map.has(s)) map.set(s, []);
			map.get(s)!.push(e);
		}
		return [...map.entries()]
			.sort((a, b) => a[0] - b[0])
			.map(([season, list]) => {
				const dates = list.map((e) => e.vod_date).filter((d): d is string => !!d).sort();
				return { season: season || null, eps: list, first: dates[0] ?? null, last: dates.at(-1) ?? null };
			});
	});

	function dotPos(e: EpisodeRelease, first: string | null, last: string | null): number {
		if (!e.vod_date || !first || !last || first === last) return 50;
		const t0 = +new Date(first), t1 = +new Date(last), t = +new Date(e.vod_date);
		return Math.max(0, Math.min(100, ((t - t0) / (t1 - t0)) * 100));
	}

	function shortDate(d: string | null): string {
		if (!d) return '';
		const [, mo, day] = d.split('-');
		return `${Number(day)}. ${Number(mo)}.`;
	}

	function cadenceLabel(days: number | null | undefined): string | null {
		if (days == null) return null;
		if (days <= 0) return 'celá séria naraz';
		if (days === 1) return 'denně';
		if (days <= 4) return `ob ${days} dny`;
		if (days <= 10) return 'týdně';
		return `ob ~${days} dní`;
	}

	function ratingColor(r: number | null) {
		if (!r) return 'var(--text-muted)';
		if (r >= 70) return '#4caf50';
		if (r >= 50) return 'var(--amber)';
		return '#e57373';
	}

	function formatDate(d: string | null) {
		if (!d) return null;
		const [y, mo, day] = d.split('-');
		return `${day}. ${mo}. ${y}`;
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Escape') onclose();
	}
</script>

<svelte:window onkeydown={handleKeydown} />

{#if loading || title}
	<div
		class="modal-overlay"
		onclick={onclose}
		role="dialog"
		aria-modal="true"
		aria-label="Detail titulu"
		tabindex="-1"
	>
		<div class="modal" onclick={(e) => e.stopPropagation()} role="presentation">
			<button class="modal-close" onclick={onclose} aria-label="Zavřít">✕</button>

			{#if loading}
				<div class="modal-loading">Načítám…</div>
			{:else if title}
				{#if title.backdrop}
					<div class="modal-backdrop">
						<img src={title.backdrop} alt="" />
						<div class="backdrop-fade"></div>
					</div>
				{/if}

				<div class="modal-content">
					<div class="modal-top">
						{#if title.poster}
							<img class="modal-poster" src={title.poster} alt={title.title} />
						{/if}

						<div class="modal-info">
							<h2 class="modal-title">{title.title}</h2>
							{#if title.title_en && title.title_en !== title.title}
								<p class="modal-title-en">{title.title_en}</p>
							{/if}

							<div class="modal-meta-row">
								{#if title.rating !== null}
									<span class="modal-rating" style="color: {ratingColor(title.rating)}">
										{title.rating} %
									</span>
								{/if}
								{#if title.votes_count}
									<span class="meta-sep">({title.votes_count.toLocaleString('cs')} hodnocení)</span>
								{/if}
								{#if title.year}
									<span class="meta-sep">{title.year}</span>
								{/if}
								{#if title.runtime_min}
									<span class="meta-sep">{Math.floor(title.runtime_min / 60)}h {title.runtime_min % 60}min</span>
								{/if}
								{#if title.title_type}
									<span class="meta-sep type-badge">{title.title_type}</span>
								{/if}
								{#if title.age_rating}
									<span class="meta-sep age-badge">{title.age_rating}</span>
								{/if}
							</div>

							{#if shapeText}
								<div class="modal-shape">
									<span class="shape-text">{shapeText}</span>
									{#if title.is_running}<span class="shape-live">● běží</span>{/if}
								</div>
							{/if}

							{#if title.is_toplevel === false && title.root_title_id != null && onopentitle}
								<button
									class="jump-serial"
									type="button"
									onclick={() => onopentitle?.(title!.root_title_id!)}
								>
									<span class="jump-label">Součást seriálu</span>
									<span class="jump-cta">Zobrazit seriál →</span>
								</button>
							{/if}

							{#if title.genres.length || title.countries.length}
								<div class="modal-genres">
									{#each title.genres as g}
										<span class="pill">{g}</span>
									{/each}
									{#each title.countries as c}
										<span class="pill country-pill">{c}</span>
									{/each}
								</div>
							{/if}

							{#if title.plot}
								<p class="modal-plot">{title.plot}</p>
							{/if}

							{#if title.vods.length}
								<div class="modal-vods">
									{#each title.vods as vod}
										{#if vod.url}
											<a class="vod-btn" href={vod.url} target="_blank" rel="noopener noreferrer">
												▶ {vod.platform}
											</a>
										{:else}
											<span class="vod-badge">{vod.platform}</span>
										{/if}
									{/each}
								</div>
							{/if}

							{#if title.vod_date}
								<p class="modal-vod-date">Na VOD od {formatDate(title.vod_date)}</p>
							{/if}
						</div>
					</div>

					{#if seasons.length}
						<div class="modal-section">
							<div class="tl-head">
								<h3 class="filter-label">Časová osa dostupnosti</h3>
								{#if cadenceLabel(title.cadence_days)}
									<span class="tl-cad">{cadenceLabel(title.cadence_days)}</span>
								{/if}
							</div>
							{#each seasons as s}
								<div class="tl-season">
									<div class="tl-slabel">
										<span class="tl-sname">{s.season ? `SÉRIE ${s.season}` : 'EPIZODY'}</span>
										<span class="tl-dates">
											{shortDate(s.first)}–{shortDate(s.last)} ·
											{s.eps.length} {s.eps.length === 1 ? 'epizoda' : s.eps.length < 5 ? 'epizody' : 'epizod'}
										</span>
									</div>
									<div class="tl-track">
										<div class="tl-line"></div>
										{#each s.eps as e}
											<span
												class="tl-dot"
												style="left: {dotPos(e, s.first, s.last)}%"
												title={`${e.title} · ${shortDate(e.vod_date)}`}
											></span>
										{/each}
									</div>
								</div>
							{/each}
						</div>
					{/if}

					{#if title.directors.length || title.screenwriters.length || title.cinematographers.length || title.composers.length || title.actors.length}
						<div class="modal-section">
							<h3 class="filter-label">Tvůrci</h3>
							<dl class="modal-crew-list">
								{#if title.directors.length}
									<div class="crew-row"><dt>Režie</dt><dd>{title.directors.join(', ')}</dd></div>
								{/if}
								{#if title.screenwriters.length}
									<div class="crew-row"><dt>Scénář</dt><dd>{title.screenwriters.join(', ')}</dd></div>
								{/if}
								{#if title.cinematographers.length}
									<div class="crew-row"><dt>Kamera</dt><dd>{title.cinematographers.join(', ')}</dd></div>
								{/if}
								{#if title.composers.length}
									<div class="crew-row"><dt>Hudba</dt><dd>{title.composers.join(', ')}</dd></div>
								{/if}
								{#if title.actors.length}
									<div class="crew-row">
										<dt>Hrají</dt>
										<dd>
											{(actorsExpanded ? title.actors : title.actors.slice(0, ACTOR_LIMIT)).join(', ')}
											{#if title.actors.length > ACTOR_LIMIT}
												<button class="more-toggle" type="button" onclick={() => (actorsExpanded = !actorsExpanded)}>
													{actorsExpanded ? 'méně' : `+ ${title.actors.length - ACTOR_LIMIT} více`}
												</button>
											{/if}
										</dd>
									</div>
								{/if}
							</dl>
						</div>
					{/if}

					{#if title.trailer_youtube_id}
						<div class="modal-trailer">
							<iframe
								src="https://www.youtube.com/embed/{title.trailer_youtube_id}"
								title="Trailer"
								frameborder="0"
								allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
								allowfullscreen
							></iframe>
						</div>
					{/if}

					{#if title.reviews.length}
						<div class="modal-reviews">
							<h3 class="filter-label">Recenze</h3>
							{#each title.reviews as review}
								<div class="review-item">
									{#if review.stars !== null}
										<div class="stars">{'★'.repeat(review.stars)}{'☆'.repeat(5 - review.stars)}</div>
									{/if}
									{#if review.author}
										<span class="review-author">{review.author}</span>
									{/if}
									{#if review.text}
										<p class="review-text">{review.text}</p>
									{/if}
								</div>
							{/each}
						</div>
					{/if}

					{#if title.link}
						<a class="modal-csfd-link" href={title.link} target="_blank" rel="noopener noreferrer">
							Otevřít na ČSFD →
						</a>
					{/if}
				</div>
			{/if}
		</div>
	</div>
{/if}

<style>
	.modal-overlay {
		position: fixed;
		inset: 0;
		background: rgba(0, 0, 0, 0.75);
		z-index: 200;
		display: flex;
		align-items: center;
		justify-content: center;
		padding: 1rem;
		backdrop-filter: blur(4px);
	}

	.modal {
		background: var(--navy-800);
		border-radius: var(--radius);
		border: 1px solid var(--border);
		width: 100%;
		max-width: 820px;
		max-height: 90vh;
		overflow-y: auto;
		position: relative;
		scrollbar-width: thin;
		scrollbar-color: var(--navy-500) transparent;
	}

	.modal-close {
		position: sticky;
		top: 0.75rem;
		float: right;
		margin: 0.75rem 0.75rem 0 0;
		background: rgba(0, 0, 0, 0.5);
		border: none;
		border-radius: 50%;
		width: 32px;
		height: 32px;
		color: var(--text-primary);
		font-size: 0.9rem;
		cursor: pointer;
		z-index: 10;
		display: flex;
		align-items: center;
		justify-content: center;
	}

	.modal-loading {
		padding: 4rem;
		text-align: center;
		color: var(--text-muted);
	}

	.modal-backdrop {
		position: relative;
		height: 200px;
		overflow: hidden;
		border-radius: var(--radius) var(--radius) 0 0;
	}

	.modal-backdrop img {
		width: 100%;
		height: 100%;
		object-fit: cover;
		object-position: center 30%;
	}

	.backdrop-fade {
		position: absolute;
		inset: 0;
		background: linear-gradient(to bottom, transparent 30%, var(--navy-800));
	}

	.modal-content {
		padding: 1.5rem;
	}

	.modal-top {
		display: flex;
		gap: 1.5rem;
		margin-bottom: 1.25rem;
	}

	.modal-poster {
		width: 110px;
		min-width: 110px;
		border-radius: var(--radius-sm);
		object-fit: cover;
		margin-top: -60px;
		position: relative;
		z-index: 1;
		box-shadow: 0 8px 24px rgba(0, 0, 0, 0.5);
	}

	.modal-title {
		font-family: 'Playfair Display', Georgia, serif;
		font-size: 1.4rem;
		line-height: 1.2;
		margin-bottom: 0.25rem;
	}

	.modal-title-en {
		color: var(--text-muted);
		font-size: 0.85rem;
		margin-bottom: 0.5rem;
	}

	.modal-meta-row {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		flex-wrap: wrap;
		margin-bottom: 0.75rem;
		font-size: 0.85rem;
	}

	.modal-rating {
		font-weight: 700;
		font-size: 1rem;
	}

	.meta-sep {
		color: var(--text-muted);
	}

	.type-badge {
		background: var(--navy-600);
		padding: 2px 8px;
		border-radius: 999px;
		font-size: 0.75rem;
		color: var(--text-secondary);
	}

	.age-badge {
		background: var(--navy-600);
		padding: 2px 8px;
		border-radius: 999px;
		font-size: 0.75rem;
		color: #e57373;
	}

	.modal-genres {
		display: flex;
		flex-wrap: wrap;
		gap: 0.4rem;
		margin-bottom: 0.75rem;
	}

	.modal-plot {
		color: var(--text-secondary);
		font-size: 0.9rem;
		line-height: 1.6;
		margin-bottom: 0.75rem;
	}

	.country-pill {
		opacity: 0.6;
	}

	.modal-vods {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem;
		margin-top: 1rem;
	}

	.vod-btn {
		display: inline-flex;
		align-items: center;
		gap: 0.35rem;
		padding: 0.45rem 1rem;
		background: var(--amber);
		color: var(--navy-900);
		font-weight: 700;
		font-size: 0.85rem;
		border-radius: var(--radius-sm);
		text-decoration: none;
		transition: opacity 0.15s;
	}

	.vod-btn:hover {
		opacity: 0.85;
	}

	.modal-vod-date {
		font-size: 0.8rem;
		color: var(--text-muted);
		margin-top: 0.75rem;
	}

	.modal-section {
		margin-top: 1.5rem;
	}

	.modal-crew-list {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}

	.crew-row {
		display: grid;
		grid-template-columns: 90px 1fr;
		gap: 0.5rem;
	}

	.crew-row dt {
		color: var(--text-muted);
		font-size: 0.85rem;
	}

	.crew-row dd {
		color: var(--text-secondary);
		font-size: 0.85rem;
		line-height: 1.5;
	}

	.more-toggle {
		background: none;
		border: none;
		padding: 0;
		margin-left: 0.35rem;
		color: var(--amber);
		font-size: 0.8rem;
		cursor: pointer;
		white-space: nowrap;
	}

	.more-toggle:hover {
		text-decoration: underline;
	}

	.modal-csfd-link {
		display: inline-block;
		margin-top: 1.5rem;
		color: var(--text-muted);
		font-size: 0.8rem;
		text-decoration: none;
	}

	.modal-csfd-link:hover {
		color: var(--amber);
	}

	.modal-trailer {
		margin-top: 1rem;
		border-radius: var(--radius-sm);
		overflow: hidden;
	}

	.modal-trailer iframe {
		width: 100%;
		aspect-ratio: 16/9;
		display: block;
	}

	.modal-reviews {
		margin-top: 1.5rem;
		display: flex;
		flex-direction: column;
		gap: 1rem;
	}

	.review-item {
		background: var(--navy-700);
		border-radius: var(--radius-sm);
		padding: 0.75rem 1rem;
	}

	.review-author {
		font-size: 0.8rem;
		font-weight: 600;
		color: var(--text-secondary);
		margin-left: 0.5rem;
	}

	.review-text {
		font-size: 0.85rem;
		color: var(--text-muted);
		margin-top: 0.4rem;
		line-height: 1.55;
	}

	.filter-label {
		font-size: 0.7rem;
		font-weight: 700;
		letter-spacing: 0.08em;
		text-transform: uppercase;
		color: var(--text-muted);
		margin-bottom: 0.5rem;
	}

	/* Serial shape line */
	.modal-shape {
		display: flex;
		align-items: center;
		gap: 0.6rem;
		margin-bottom: 0.75rem;
	}

	.shape-text {
		font-size: 0.9rem;
		font-weight: 600;
		color: var(--amber);
	}

	.shape-live {
		font-size: 0.72rem;
		font-weight: 700;
		letter-spacing: 0.04em;
		text-transform: uppercase;
		padding: 2px 8px;
		border-radius: 999px;
		background: rgba(74, 222, 128, 0.16);
		color: #4ade80;
		border: 1px solid rgba(74, 222, 128, 0.35);
	}

	/* Jump-to-serial banner (release → work) */
	.jump-serial {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 1rem;
		width: 100%;
		margin: 0.25rem 0 0.75rem;
		padding: 0.6rem 0.9rem;
		background: rgba(245, 166, 35, 0.08);
		border: 1px solid rgba(245, 166, 35, 0.25);
		border-radius: var(--radius-sm);
		cursor: pointer;
		text-align: left;
		transition: background 0.15s;
	}

	.jump-serial:hover {
		background: rgba(245, 166, 35, 0.14);
	}

	.jump-label {
		font-size: 0.8rem;
		color: var(--text-secondary);
	}

	.jump-cta {
		font-size: 0.85rem;
		font-weight: 700;
		color: var(--amber);
		white-space: nowrap;
	}

	/* Release timeline */
	.tl-head {
		display: flex;
		align-items: baseline;
		gap: 0.6rem;
		margin-bottom: 1rem;
	}

	.tl-cad {
		margin-left: auto;
		font-size: 0.75rem;
		color: #4ade80;
	}

	.tl-season {
		margin-bottom: 1.1rem;
	}

	.tl-slabel {
		display: flex;
		align-items: baseline;
		gap: 0.6rem;
		margin-bottom: 0.6rem;
		flex-wrap: wrap;
	}

	.tl-sname {
		font-family: ui-monospace, 'SF Mono', Menlo, monospace;
		font-size: 0.75rem;
		color: var(--amber);
		font-weight: 700;
	}

	.tl-dates {
		font-size: 0.75rem;
		color: var(--text-muted);
	}

	.tl-track {
		position: relative;
		height: 22px;
	}

	.tl-line {
		position: absolute;
		top: 10px;
		left: 0;
		right: 0;
		height: 2px;
		background: var(--navy-500);
		border-radius: 2px;
	}

	.tl-dot {
		position: absolute;
		top: 5px;
		width: 10px;
		height: 10px;
		border-radius: 50%;
		background: var(--amber);
		transform: translateX(-50%);
		border: 2px solid var(--navy-800);
		cursor: help;
	}
</style>

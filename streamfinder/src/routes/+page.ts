import type { PageLoad } from './$types';

export const load: PageLoad = async ({ parent }) => {
	const { titles, dimensions } = await parent();

	const today = new Date();
	const daysAgo = (n: number) => {
		const d = new Date(today);
		d.setDate(d.getDate() - n);
		return d.toISOString().slice(0, 10);
	};

	const todayStr = today.toISOString().slice(0, 10);

	// ── Featured carousel ─────────────────────────────────────────────────────
	//
	// The carousel must read as a cross-section of the catalog, not as one genre's
	// greatest hits. Two mechanisms, doing two different jobs — a single score
	// cannot do both.
	//
	// RANKING — confidence, not popularity. The old score multiplied the rating by
	// min(1, votes/500), which rewards being famous. While votes_count was truncated
	// at its first thousands group that stayed hidden; once the counts were correct,
	// the carousel collapsed onto five Nolan films whose scores had jumped ~47%.
	// A vote FLOOR is no better: votes accumulate with age, so in the 0–7 day slice
	// the median is 0 votes and only 25% would clear a floor of 50, against 79% at
	// 31–45 days. A floor filters age, not quality, and hits hardest exactly the
	// releases a carousel exists to show.
	// Measuring the pool says what the vote count actually carries: mean rating by
	// vote band is 56.5 / 59.6 / 59.4 / 66.3 / 66.9 — low-vote titles are NOT
	// systematically overrated (their mean is lower) — but their spread is nearly
	// double (sd 19.9 vs 10.8) and 9% of them exceed 90% against ~1% at high votes.
	// That is noise, not bias, so the fix is shrinkage toward the pool mean: extremes
	// get pulled in, nobody gets excluded, and a new title competes from day one.
	//
	// DIVERSITY — quotas. Shrinkage alone will not do it: The Dark Knight still
	// scores 91 and still wins. Slots are the only thing that guarantees a mix.
	const FEATURED_COUNT = 5;
	const SHRINK_K = 40; // ≈ the vote count at which the spread above settles down
	const MIN_SERIALS = 2; // films outnumber serials 3:1 and rate higher — reserve seats
	const MAX_LEGACY = 1; // a classic landing on VOD is news; five of them is not
	const MAX_PER_GENRE = 2; // breaks up a single franchise (it was 4/5 "Akční")
	const RECENT_FROM = today.getFullYear() - 2; // "the last ~2 years"

	const isFeaturable = (t: (typeof titles)[number]) =>
		Boolean(t.poster) &&
		(t.title_type === 'film' ||
			(t.is_toplevel && (t.title_type === 'seriál' || t.title_type === 'tv film')));

	// Freshness only breaks ties between comparable titles — it never outranks quality.
	const daysSince = (iso: string) =>
		Math.max(0, Math.round((today.getTime() - new Date(iso).getTime()) / 86_400_000));

	const pickFeatured = (count: number) => {
		for (const days of [45, 75, 120] as const) {
			const cands = titles.filter(
				(t) =>
					t.vod_date && t.vod_date >= daysAgo(days) && t.vod_date <= todayStr && isFeaturable(t)
			);
			if (cands.length < count) continue;

			// Prior = the mean rating of everything rated in this window, so the
			// shrinkage target moves with the pool instead of being a magic number.
			const rated = cands.filter((t) => t.rating !== null);
			const prior = rated.length
				? rated.reduce((s, t) => s + (t.rating ?? 0), 0) / rated.length
				: 65;

			// An unrated title shrinks to exactly the prior: mid-pack, so a brand-new
			// release can still take a slot a quota needs, but never leads on nothing.
			const score = (t: (typeof titles)[number]) => {
				const votes = t.votes_count ?? 0;
				const rating = t.rating ?? prior;
				return (rating * votes + prior * SHRINK_K) / (votes + SHRINK_K);
			};

			const ranked = [...cands].sort((a, b) => {
				const d = score(b) - score(a);
				return d !== 0 ? d : daysSince(a.vod_date!) - daysSince(b.vod_date!);
			});

			// Greedy pick under the quotas, then a second pass that fills any slot the
			// quotas could not — an under-full carousel is worse than a repeated genre.
			const picked: typeof ranked = [];
			const genreUsed = new Map<string, number>();
			let serials = 0;
			let legacy = 0;

			const take = (t: (typeof ranked)[number]) => {
				picked.push(t);
				genreUsed.set(t.genres[0] ?? '—', (genreUsed.get(t.genres[0] ?? '—') ?? 0) + 1);
				if (t.title_type === 'seriál') serials++;
				if ((t.year ?? 0) < RECENT_FROM) legacy++;
			};

			for (const t of ranked) {
				if (picked.length === count) break;
				if ((t.year ?? 0) < RECENT_FROM && legacy >= MAX_LEGACY) continue;
				if ((genreUsed.get(t.genres[0] ?? '—') ?? 0) >= MAX_PER_GENRE) continue;
				// Keep seats free for serials while only films are left to fill them.
				const seatsLeft = count - picked.length;
				if (t.title_type !== 'seriál' && seatsLeft <= MIN_SERIALS - serials) continue;
				take(t);
			}
			if (picked.length < count) {
				for (const t of ranked) {
					if (picked.length === count) break;
					if (!picked.includes(t)) take(t);
				}
			}
			if (picked.length === count) return picked;
		}
		return titles
			.filter((t) => t.vod_date && t.vod_date <= todayStr && isFeaturable(t))
			.sort((a, b) => (b.rating ?? 0) - (a.rating ?? 0))
			.slice(0, count);
	};

	const featuredList = pickFeatured(FEATURED_COUNT);
	const featuredIds = new Set(featuredList.map((t) => t.id));

	// ── Curated editorial rails ──────────────────────────────────────────────
	const isWork = (t: (typeof titles)[number]) => t.is_toplevel !== false;
	// A work's most recent VOD activity — its own release, or a serial's last
	// episode — so a running show with a fresh episode counts as "recent".
	const recencyDate = (t: (typeof titles)[number]) => {
		const own = t.vod_date ?? '';
		const last = t.last_vod_date ?? '';
		return own > last ? own : last;
	};

	// Právě přibylo — most recently active works (past ~10 days)
	const addedCut = daysAgo(10);
	const justAdded = titles
		.filter((t) => isWork(t) && recencyDate(t) >= addedCut && recencyDate(t) <= todayStr)
		.sort((a, b) => recencyDate(b).localeCompare(recencyDate(a)))
		.slice(0, 18);

	// Nejlíp hodnocené tento měsíc — quality first, but needs a few votes to be
	// real; relax the vote bar if too few titles clear it.
	// Excludes whatever the carousel already shows — its top five WERE this rail's
	// top five, so the page opened with the same titles twice in a row.
	const monthCut = daysAgo(35);
	const ratedRecent = titles.filter(
		(t) =>
			isWork(t) &&
			!featuredIds.has(t.id) &&
			t.vod_date &&
			t.vod_date >= monthCut &&
			(t.rating ?? 0) > 0
	);
	let bestThisMonth = ratedRecent
		.filter((t) => (t.votes_count ?? 0) >= 50)
		.sort((a, b) => (b.rating ?? 0) - (a.rating ?? 0))
		.slice(0, 18);
	if (bestThisMonth.length < 8) {
		bestThisMonth = ratedRecent.sort((a, b) => (b.rating ?? 0) - (a.rating ?? 0)).slice(0, 18);
	}

	// Seriály, co právě běží
	const runningSerials = titles
		.filter((t) => isWork(t) && t.is_running)
		.sort((a, b) => recencyDate(b).localeCompare(recencyDate(a)))
		.slice(0, 18);

	// Skryté klenoty — highly rated, but few people have seen them.
	//
	// "High rating + few votes" on its own hands the rail to fan content. A concert
	// film is rated by the band's devotees, so it sits at 95–99% where no drama ever
	// reaches: 12 of 18 slots were live recordings. Note the vote count is NOT the
	// culprit — average rating is flat across the vote bands (86.0 / 86.0 / 85.4 /
	// 85.7), so sorting by rating alone is what does it. Two corrections, both
	// measured against the real catalog rather than guessed:
	//
	//   1. Drop formats whose rating measures devotion to the subject rather than the
	//      work itself — the same reasoning the art-films rail below uses.
	//   2. Cap how many slots one genre may take. Without it documentaries alone fill
	//      14 of 18, because they draw the same self-selecting audience.
	//
	// The vote floor rises 30 → 80: under 80 votes a rating is barely evidence.
	// Known limitation: ČSFD files some stand-up specials under "Komedie", so a few
	// still slip through. Left alone rather than pattern-matched on titles.
	const FAN_FORMAT_GENRES = new Set([
		'Hudební',
		'Sportovní',
		'Reality-TV',
		'Soutěžní',
		'Stand-up',
		'Talk-show',
		'Telenovela',
		'Erotický',
		'Pornografický'
	]);
	const GEM_GENRE_CAP = 4;
	const GEM_RAIL_SIZE = 18;

	const gemPool = titles
		.filter(
			(t) =>
				isWork(t) &&
				(t.rating ?? 0) >= 82 &&
				(t.votes_count ?? 0) >= 80 &&
				(t.votes_count ?? 0) <= 800 &&
				t.title_type !== 'divadelní záznam' &&
				!t.genres.some((g) => FAN_FORMAT_GENRES.has(g))
		)
		.sort((a, b) => (b.rating ?? 0) - (a.rating ?? 0));

	const gemGenreUsed = new Map<string, number>();
	const hiddenGems: typeof gemPool = [];
	for (const t of gemPool) {
		const lead = t.genres[0] ?? '—';
		const used = gemGenreUsed.get(lead) ?? 0;
		if (used >= GEM_GENRE_CAP) continue;
		gemGenreUsed.set(lead, used + 1);
		hiddenGems.push(t);
		if (hiddenGems.length === GEM_RAIL_SIZE) break;
	}

	// Artové filmy — a composite score, not a single threshold. Neither "low votes"
	// nor "Drama" alone is selective: votes_count is biased by era and platform reach
	// (a 1965 arthouse film can't out-vote a 2024 Netflix drop), and Drama is simply
	// the largest genre (a third of the catalog). So: rare CSFD genre tags that are
	// genuine stylistic markers (Experimentální, Film-Noir, Poetický…) count far more
	// than the broad ones; "obscurity" is the film's votes_count percentile within
	// its own decade, not an absolute count; and a few mainstream/fandom genres
	// (Hudební, Sportovní, Reality-TV…) actively pull the score down — otherwise
	// concert-film and "making of" documentaries (excluded by title below) dominate
	// on rating+low-votes alone.
	const RARE_ART_GENRES = new Set([
		'Experimentální', 'Film-Noir', 'Poetický', 'Podobenství', 'Povídkový', 'Psychologický'
	]);
	const SOFT_ART_GENRES = new Set(['Drama', 'Dokumentární', 'Životopisný', 'Krátkometrážní']);
	const MAINSTREAM_GENRES = new Set([
		'Akční', 'Sci-Fi', 'Fantasy', 'Horor', 'Rodinný', 'Animovaný', 'Muzikál', 'Western',
		'Dobrodružný', 'Hudební', 'Sportovní', 'Reality-TV', 'Soutěžní', 'Stand-up', 'Talk-show',
		'Katastrofický', 'Telenovela', 'Pohádka', 'Naučný', 'Erotický', 'Pornografický'
	]);
	const ART_TAGS = new Set(['festival', 'surrealismus', 'avantgarda', 'černobílý film']);
	// Franchise/promo shorts ("Jak vznikal…", "Making of…") share Dokumentární +
	// Krátkometrážní with real short-form documentaries but aren't films in their
	// own right — exclude by title since no field marks them as bonus content.
	const MAKING_OF_RE = /^(jak (vznikal|se nat[aá]čel|se d[eě]lal)|making of|tvorb[ay] (seri[aá]lu|filmu))/i;
	const hasAny = (have: string[], want: Set<string>) => have.some((g) => want.has(g));

	const isArtBase = (t: (typeof titles)[number]) =>
		t.title_type === 'film' && Boolean(t.poster) && Boolean(t.year) && !MAKING_OF_RE.test(t.title);

	// A KVIFF (Karlovy Vary) mention in the plot or a review is a curatorial fact —
	// the film was actually selected for the Czech A-list festival — not an inferred
	// heuristic. So it bypasses the rating/votes floor below: a challenging arthouse
	// pick often gets a mixed or low audience score on ČSFD precisely because it's
	// uncompromising, and a brand-new festival premiere hasn't accumulated votes yet.
	const artCandidates = titles.filter(
		(t) => isArtBase(t) && (t.kviff || (t.rating !== null && (t.votes_count ?? 0) >= 40))
	);

	// Relative obscurity: percentile rank of votes_count within its own decade.
	const decadeGroups = new Map<number, typeof artCandidates>();
	for (const t of artCandidates) {
		const decade = Math.floor((t.year as number) / 10) * 10;
		if (!decadeGroups.has(decade)) decadeGroups.set(decade, []);
		decadeGroups.get(decade)!.push(t);
	}
	const votesPercentile = new Map<number, number>();
	for (const group of decadeGroups.values()) {
		const sorted = [...group].sort((a, b) => (a.votes_count ?? 0) - (b.votes_count ?? 0));
		sorted.forEach((t, i) =>
			votesPercentile.set(t.id, sorted.length > 1 ? i / (sorted.length - 1) : 0.5)
		);
	}

	const clamp01 = (x: number) => Math.max(0, Math.min(1, x));

	const artScore = (t: (typeof artCandidates)[number]) => {
		const quality = clamp01(((t.rating ?? 0) - 65) / 30);
		const obscurity = 1 - (votesPercentile.get(t.id) ?? 0.5);
		const genreScore =
			(hasAny(t.genres, RARE_ART_GENRES) ? 1.6 : 0) +
			(hasAny(t.genres, SOFT_ART_GENRES) ? 0.4 : 0) -
			(hasAny(t.genres, MAINSTREAM_GENRES) ? 0.8 : 0);
		const tagBonus = hasAny(t.tags, ART_TAGS) ? 1 : 0;
		const originBonus = !t.countries.includes('USA') && !t.countries.includes('Velká Británie') ? 1 : 0;
		return 2.5 * quality + 1.5 * obscurity + 2 * genreScore + tagBonus + 0.4 * originBonus;
	};

	const ART_RAIL_SIZE = 18;
	const KVIFF_SLOTS = 8;

	// Two tiers, not one blended score: a flat KVIFF bonus large enough to guarantee
	// inclusion would also let it dominate every slot (there are more KVIFF-tagged
	// films some months than the whole rail), crowding out the score-only discoveries
	// that are the point of this section. Reserved slots keep both visible.
	const kviffPool = artCandidates
		.filter((t) => t.kviff)
		.map((t) => ({ t, s: artScore(t) }))
		.sort((a, b) => b.s - a.s);
	const otherPool = artCandidates
		.filter((t) => !t.kviff)
		.map((t) => ({ t, s: artScore(t) }))
		.filter(({ s }) => s >= 4)
		.sort((a, b) => b.s - a.s);

	const kviffTaken = Math.min(KVIFF_SLOTS, kviffPool.length);
	const artFilms = [...kviffPool.slice(0, kviffTaken), ...otherPool.slice(0, ART_RAIL_SIZE - kviffTaken)]
		.slice(0, ART_RAIL_SIZE)
		.map(({ t }) => t);

	// Stats. `total` counts WORKS, not rows: a third of the index is episodes and
	// seasons, which the Katalóg never lists. Counting them made the headline
	// promise 49883 titles and then show 33929.
	const stats = {
		total: titles.filter(isWork).length,
		films: titles.filter((t) => t.title_type === 'film').length,
		platforms: dimensions.platforms.length,
		genres: dimensions.genres.length,
		avgRating: Math.round(
			titles.filter((t) => t.rating !== null).reduce((s, t) => s + (t.rating ?? 0), 0) /
				titles.filter((t) => t.rating !== null).length
		),
	};

	return {
		featuredList,
		justAdded,
		bestThisMonth,
		runningSerials,
		hiddenGems,
		artFilms,
		stats,
		dimensions
	};
};

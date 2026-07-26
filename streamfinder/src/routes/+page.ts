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

	// Featured carousel: the 4–5 most interesting recent works. A hero slide needs an
	// image, so a poster is mandatory. "Interesting" = rating tempered by how many
	// people voted (fresh releases have few votes, so don't let a 90% / 12-vote fluke
	// outrank a well-established 82%). Widen the window progressively until we have
	// enough slides — there is always a set.
	const FEATURED_COUNT = 5;

	const isFeaturable = (t: (typeof titles)[number]) =>
		Boolean(t.poster) &&
		(t.title_type === 'film' ||
			(t.is_toplevel && (t.title_type === 'seriál' || t.title_type === 'tv film')));

	const featuredScore = (t: (typeof titles)[number]) => {
		const rating = t.rating ?? 0;
		const votes = t.votes_count ?? 0;
		const voteWeight = Math.min(1, votes / 500); // full confidence at ~500 votes
		return rating * (0.6 + 0.4 * voteWeight);
	};

	const pickFeatured = (count: number) => {
		for (const [days, minRating] of [
			[45, 65],
			[75, 62],
			[120, 60],
		] as const) {
			const cands = titles
				.filter(
					(t) =>
						t.vod_date &&
						t.vod_date >= daysAgo(days) &&
						t.vod_date <= todayStr &&
						isFeaturable(t) &&
						(t.rating ?? 0) >= minRating
				)
				.sort((a, b) => featuredScore(b) - featuredScore(a));
			if (cands.length >= count) return cands.slice(0, count);
		}
		// last resort: best-scored recent works with a poster, whatever the rating
		return titles
			.filter((t) => t.vod_date && t.vod_date <= todayStr && isFeaturable(t))
			.sort((a, b) => featuredScore(b) - featuredScore(a))
			.slice(0, count);
	};

	const featuredList = pickFeatured(FEATURED_COUNT);

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
	const monthCut = daysAgo(35);
	const ratedRecent = titles.filter(
		(t) => isWork(t) && t.vod_date && t.vod_date >= monthCut && (t.rating ?? 0) > 0
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

	// Skryté klenoty — highly rated, but few people have seen them
	const hiddenGems = titles
		.filter(
			(t) =>
				isWork(t) &&
				(t.rating ?? 0) >= 82 &&
				(t.votes_count ?? 0) >= 30 &&
				(t.votes_count ?? 0) <= 800
		)
		.sort((a, b) => (b.rating ?? 0) - (a.rating ?? 0))
		.slice(0, 18);

	// Stats
	const stats = {
		total: titles.length,
		films: titles.filter((t) => t.title_type === 'film').length,
		platforms: dimensions.platforms.length,
		genres: dimensions.genres.length,
		avgRating: Math.round(
			titles.filter((t) => t.rating !== null).reduce((s, t) => s + (t.rating ?? 0), 0) /
				titles.filter((t) => t.rating !== null).length
		),
	};

	return { featuredList, justAdded, bestThisMonth, runningSerials, hiddenGems, stats, dimensions };
};

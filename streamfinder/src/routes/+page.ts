import type { PageLoad } from './$types';

export const load: PageLoad = async ({ parent }) => {
	const { titles, dimensions } = await parent();

	const today = new Date();
	const daysAgo = (n: number) => {
		const d = new Date(today);
		d.setDate(d.getDate() - n);
		return d.toISOString().slice(0, 10);
	};

	const thisMonthStart = today.toISOString().slice(0, 7) + '-01';
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

	// New this week (past 7 days)
	const weekCutoff = daysAgo(7);
	const newThisWeek = titles
		.filter((t) => t.vod_date && t.vod_date >= weekCutoff)
		.sort((a, b) => (b.vod_date ?? '') > (a.vod_date ?? '') ? 1 : -1)
		.slice(0, 20);

	// Recent arrivals grouped by date (past 14 days)
	const twoWeekCutoff = daysAgo(14);
	const recentByDate = new Map<string, number>();
	titles
		.filter((t) => t.vod_date && t.vod_date >= twoWeekCutoff)
		.forEach((t) => {
			const d = t.vod_date!;
			recentByDate.set(d, (recentByDate.get(d) ?? 0) + 1);
		});
	const recentDates = [...recentByDate.entries()]
		.sort(([a], [b]) => b.localeCompare(a))
		.slice(0, 7);

	// Best rated this month
	const bestThisMonth = titles
		.filter(
			(t) =>
				t.vod_date &&
				t.vod_date >= thisMonthStart &&
				t.rating !== null
		)
		.sort((a, b) => (b.rating ?? 0) - (a.rating ?? 0))
		.slice(0, 20);

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

	return { featuredList, newThisWeek, bestThisMonth, recentDates, stats, dimensions };
};

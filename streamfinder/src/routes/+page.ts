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

	// Featured title: the best recent work. Very fresh releases have few votes yet, so
	// relax the bar progressively (window / rating / votes) — there is always a pick.
	const isFeaturable = (t: (typeof titles)[number]) =>
		t.title_type === 'film' || (t.is_toplevel && (t.title_type === 'seriál' || t.title_type === 'tv film'));

	const featuredTiers: [number, number, number][] = [
		[21, 75, 100],
		[45, 72, 50],
		[60, 70, 20],
		[90, 68, 5],
		[120, 0, 0], // last resort: highest-rated recent work, whatever the votes
	];

	const findFeatured = (days: number, minRating: number, minVotes: number) =>
		titles
			.filter(
				(t) =>
					t.vod_date &&
					t.vod_date >= daysAgo(days) &&
					t.vod_date <= todayStr &&
					isFeaturable(t) &&
					(t.rating ?? 0) >= minRating &&
					(t.votes_count ?? 0) >= minVotes
			)
			.sort((a, b) => (b.rating ?? 0) - (a.rating ?? 0))[0] ?? null;

	let featured = null;
	for (const [days, r, v] of featuredTiers) {
		featured = findFeatured(days, r, v);
		if (featured) break;
	}

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

	return { featured, newThisWeek, bestThisMonth, recentDates, stats, dimensions };
};

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

	// Featured title: highest-rated film from past 21 days, rating>=75, votes>=500
	const recentCutoff21 = daysAgo(21);
	const recentCutoff45 = daysAgo(45);

	const findFeatured = (cutoff: string) =>
		titles
			.filter(
				(t) =>
					t.vod_date &&
					t.vod_date >= cutoff &&
					t.vod_date <= today.toISOString().slice(0, 10) &&
					(t.rating ?? 0) >= 75 &&
					(t.votes_count ?? 0) >= 500 &&
					t.title_type === 'film'
			)
			.sort((a, b) => (b.rating ?? 0) - (a.rating ?? 0))[0] ?? null;

	const featured = findFeatured(recentCutoff21) ?? findFeatured(recentCutoff45) ?? null;

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

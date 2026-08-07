import type { PageLoad } from './$types';
import { loadTitles } from '$lib/data/titles';

export const load: PageLoad = async ({ parent, url, fetch }) => {
	const [{ dimensions }, titles] = await Promise.all([parent(), loadTitles(fetch)]);

	function get(key: string): string | null {
		try { return url.searchParams.get(key); } catch { return null; }
	}
	function parseNum(s: string | null): number | null {
		if (!s) return null;
		const n = parseInt(s, 10);
		return isNaN(n) ? null : n;
	}

	// Guard against Number('') === 0 edge case when ?days= is present but empty
	const rawDays = get('days');
	const initialDays = rawDays ? Math.min(Math.max(Number(rawDays), 28), 365) : 28;

	return {
		titles,
		dimensions,
		initialDays,
		// Same filter params as Katalog
		initialQuery: get('q') ?? '',
		initialGenres: get('genre')?.split(',').filter(Boolean) ?? [],
		initialPlatforms: get('platform')?.split(',').filter(Boolean) ?? [],
		initialCountries: get('country')?.split(',').filter(Boolean) ?? [],
		initialTags: get('tag')?.split(',').filter(Boolean) ?? [],
		// Comma-separated like the other facets. A bare ?type=film still works,
		// so links shared while this was single-select keep resolving.
		initialFavoritesOnly: get('fav') === '1',
		initialTypes: get('type')?.split(',').filter(Boolean) ?? [],
		initialYearFrom: parseNum(get('yearFrom')),
		initialYearTo: parseNum(get('yearTo')),
		initialRatingMin: parseNum(get('ratingMin')),
		initialCrew: url.searchParams.getAll('crew').filter(Boolean),
	};
};

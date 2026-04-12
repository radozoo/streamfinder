import type { PageLoad } from './$types';

export const load: PageLoad = async ({ parent, url }) => {
	const { titles, dimensions } = await parent();

	const validSorts = ['rating', 'year', 'vod_date', 'votes'] as const;
	type SortKey = (typeof validSorts)[number];

	function get(key: string): string | null {
		try { return url.searchParams.get(key); } catch { return null; }
	}

	function parseNum(s: string | null): number | null {
		if (!s) return null;
		const n = parseInt(s, 10);
		return isNaN(n) ? null : n;
	}

	const sortParam = get('sort');

	return {
		titles,
		dimensions,
		initialQuery: get('q') ?? '',
		initialGenres: get('genre')?.split(',').filter(Boolean) ?? [],
		initialPlatforms: get('platform')?.split(',').filter(Boolean) ?? [],
		initialCountries: get('country')?.split(',').filter(Boolean) ?? [],
		initialTags: get('tag')?.split(',').filter(Boolean) ?? [],
		initialType: get('type') ?? '',
		initialYearFrom: parseNum(get('yearFrom')),
		initialYearTo: parseNum(get('yearTo')),
		initialRatingMin: parseNum(get('ratingMin')),
		initialSort: (validSorts.includes(sortParam as SortKey) ? sortParam : 'vod_date') as SortKey
	};
};

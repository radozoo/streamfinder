/**
 * Reading filter state out of a URL.
 *
 * This lives here, and is called from the components rather than from `load`, for a
 * concrete reason: a page whose `load` touches `url.searchParams` cannot be
 * prerendered. SvelteKit throws "Cannot access url.searchParams on a page with
 * prerendering enabled", and it is right to — a prerendered page is one file for
 * every query string, so its baked-in data cannot depend on one.
 *
 * Katalóg and Kalendář did exactly that. Prerendering them failed with a 500 that
 * `handleHttpError` downgraded to a warning, so the build stayed green while both
 * pages fell back to 404.html: the site's two main pages answered crawlers with
 * HTTP 404, and every visit paid for a client-side boot before seeing anything.
 *
 * The tempting fix — wrap the reads in try/catch so prerendering succeeds — would
 * have been worse than the bug. The page would prerender with its filters baked in
 * as empty, and since SvelteKit serves a prerendered page's data as-is, a shared
 * ?q=batman link would have quietly shown the unfiltered catalog. The filters
 * working today is a side effect of prerendering being broken.
 *
 * So parsing happens where a query string legitimately exists: in the browser, from
 * page.url, when the component initialises. Same functions, one definition, used by
 * both routes and by their tests.
 */

const VALID_SORTS = ['rating', 'year', 'vod_date', 'votes'] as const;
export type SortKey = (typeof VALID_SORTS)[number];

/** "Přidáno na VOD" windows, in days. Anything else is ignored. */
const VALID_RECENCY = [7, 30, 90, 180, 365, 730, 1095];

const num = (s: string | null): number | null => {
	if (!s) return null;
	const n = parseInt(s, 10);
	return isNaN(n) ? null : n;
};

/** Comma-separated facet values. A bare ?type=film still works, so links shared
 *  while a facet was single-select keep resolving. */
const list = (s: string | null): string[] => s?.split(',').filter(Boolean) ?? [];

export interface CommonFilters {
	query: string;
	genres: string[];
	platforms: string[];
	countries: string[];
	tags: string[];
	types: string[];
	crew: string[];
	favoritesOnly: boolean;
	yearFrom: number | null;
	yearTo: number | null;
	ratingMin: number | null;
}

function common(sp: URLSearchParams): CommonFilters {
	return {
		query: sp.get('q') ?? '',
		genres: list(sp.get('genre')),
		platforms: list(sp.get('platform')),
		countries: list(sp.get('country')),
		tags: list(sp.get('tag')),
		types: list(sp.get('type')),
		// Repeated params (?crew=A&crew=B), because names contain commas.
		crew: sp.getAll('crew').filter(Boolean),
		favoritesOnly: sp.get('fav') === '1',
		yearFrom: num(sp.get('yearFrom')),
		yearTo: num(sp.get('yearTo')),
		ratingMin: num(sp.get('ratingMin'))
	};
}

export function katalogFilters(sp: URLSearchParams) {
	const sort = sp.get('sort');
	const recency = num(sp.get('added'));
	return {
		...common(sp),
		sort: (VALID_SORTS.includes(sort as SortKey) ? sort : 'vod_date') as SortKey,
		recency: recency && VALID_RECENCY.includes(recency) ? recency : 0
	};
}

export const KALENDAR_DEFAULT_DAYS = 28;

export function kalendarFilters(sp: URLSearchParams) {
	// Number('') is 0, which would silently mean "no days" — hence the truthiness
	// check before clamping.
	const raw = sp.get('days');
	return {
		...common(sp),
		days: raw ? Math.min(Math.max(Number(raw), KALENDAR_DEFAULT_DAYS), 365) : KALENDAR_DEFAULT_DAYS,
		// Whether the "Připravované" section is expanded. It belongs in the URL for the
		// same reason the filters do: the component is torn down and rebuilt on every
		// navigation, so anything held only in component state is gone by the time the
		// visitor presses Back — and the section vanishing changes the page height,
		// which drops the restored scroll position into days weeks earlier.
		upcoming: sp.get('upcoming') === '1'
	};
}

/** No query string — what a prerendered page renders, and the base a component
 *  starts from before it reads the real URL in the browser. */
export const EMPTY_PARAMS = new URLSearchParams();

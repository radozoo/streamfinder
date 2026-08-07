import { base } from '$app/paths';
import type { DimEntry } from '$lib/types';

let _cache: DimEntry[] | null = null;
let _loading: Promise<DimEntry[]> | null = null;

/**
 * Lazy-load tags.json — the full 3,286 tags, for the tag search box.
 *
 * These used to sit in dimensions.json, which the root layout fetches on every
 * route: 26.4 KB of a 29.5 KB payload, paid for by every visitor on every page,
 * including a title page that shows no facets at all. The panels display the top 40
 * as a browsable pill cloud and those still ship in dimensions.json; the long tail
 * exists only so the search box can find it, so it loads when someone opens that box.
 */
export async function loadTags(fetchFn: typeof fetch = fetch): Promise<DimEntry[]> {
	if (_cache) return _cache;
	if (_loading) return _loading;

	_loading = fetchFn(`${base}/data/tags.json`)
		.then((res) => res.json())
		.then((data: DimEntry[]) => {
			_cache = data;
			_loading = null;
			return data;
		})
		.catch((err) => {
			_loading = null;
			throw err;
		});

	return _loading;
}

/** Whether the full list is already in memory (without triggering a fetch). */
export function areTagsLoaded(): boolean {
	return _cache !== null;
}

/** Tests only. The cache is module-level, so it would otherwise leak between them. */
export function __resetTagsCache(): void {
	_cache = null;
	_loading = null;
}

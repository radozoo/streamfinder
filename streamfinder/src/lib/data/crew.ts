import { base } from '$app/paths';
import type { CrewEntry } from '$lib/types';

let _cache: CrewEntry[] | null = null;
let _loading: Promise<CrewEntry[]> | null = null;

/**
 * Lazy-load crew_index.json. Fetches on first call, returns cached data after.
 */
export async function loadCrewIndex(fetchFn: typeof fetch = fetch): Promise<CrewEntry[]> {
	if (_cache) return _cache;
	if (_loading) return _loading;

	_loading = fetchFn(`${base}/data/crew_index.json`)
		.then((res) => res.json())
		.then((data: CrewEntry[]) => {
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

let _titlesCache: Map<number, number[]> | null = null;
let _titlesLoading: Promise<Map<number, number[]>> | null = null;

/**
 * Lazy-load crew_titles.json — which people worked on which title, keyed by the
 * index's `id`.
 *
 * This used to be a `crew_ids` array on every entry in titles_index.json, which
 * made it 3.97 MB of the file's 10.24 MB gzipped: unrelated integers are the one
 * thing gzip cannot squeeze, so it dominated the wire cost of a facet most
 * visitors never open. It now loads beside crew_index.json, on demand.
 */
export async function loadCrewTitles(fetchFn: typeof fetch = fetch): Promise<Map<number, number[]>> {
	if (_titlesCache) return _titlesCache;
	if (_titlesLoading) return _titlesLoading;

	_titlesLoading = fetchFn(`${base}/data/crew_titles.json`)
		.then((res) => res.json())
		.then((data: Record<string, number[]>) => {
			_titlesCache = new Map(Object.entries(data).map(([id, ids]) => [Number(id), ids]));
			_titlesLoading = null;
			return _titlesCache;
		})
		.catch((err) => {
			_titlesLoading = null;
			throw err;
		});

	return _titlesLoading;
}

/** Check if crew data is already loaded (without triggering a fetch). */
export function isCrewLoaded(): boolean {
	return _cache !== null;
}

/** Get cached crew data (returns null if not yet loaded). */
export function getCachedCrew(): CrewEntry[] | null {
	return _cache;
}

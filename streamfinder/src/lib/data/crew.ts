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

/** Check if crew data is already loaded (without triggering a fetch). */
export function isCrewLoaded(): boolean {
	return _cache !== null;
}

/** Get cached crew data (returns null if not yet loaded). */
export function getCachedCrew(): CrewEntry[] | null {
	return _cache;
}

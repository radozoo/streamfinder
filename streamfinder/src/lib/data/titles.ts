import { base } from '$app/paths';
import type { TitleIndex } from '$lib/types';

/**
 * The catalog index, loaded by the routes that actually browse it.
 *
 * It used to live in the root layout's load, so every route downloaded all 51k
 * entries — 6.28 MB gzipped — before rendering anything. A single title page needs
 * none of it: it reads its own detail shard and nothing else. The layout wanted the
 * index for exactly one thing, the footer's "last updated" date, which is now a
 * number in meta.json.
 *
 * Katalóg, Kalendář, Insights and Oblíbené genuinely need the whole catalog and ask
 * for it here. The search overlay asks when it opens.
 *
 * Cached after the first fetch, so moving between those routes costs nothing.
 */
let _cache: TitleIndex[] | null = null;
let _loading: Promise<TitleIndex[]> | null = null;

export async function loadTitles(fetchFn: typeof fetch = fetch): Promise<TitleIndex[]> {
	if (_cache) return _cache;
	if (_loading) return _loading;

	_loading = fetchFn(`${base}/data/titles_index.json`)
		.then((res) => res.json())
		.then((data: TitleIndex[]) => {
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

/** Already loaded? Lets a caller avoid a spinner it does not need. */
export function areTitlesLoaded(): boolean {
	return _cache !== null;
}

/**
 * Test-only. The cache is module-level and survives between tests, so the first
 * test's fixture would be served to every test after it — quietly, since they all
 * get a plausible-looking catalog and only their assertions disagree. Call this
 * between cases that feed load() different catalogs.
 */
export function __resetTitlesCache(): void {
	_cache = null;
	_loading = null;
}

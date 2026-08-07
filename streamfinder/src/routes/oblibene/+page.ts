import type { PageLoad } from './$types';
import { loadTitles } from '$lib/data/titles';

// The list itself lives in localStorage, so there is nothing to load per visitor —
// only the catalog, needed to turn saved ČSFD ids back into cards.
export const load: PageLoad = async ({ fetch }) => {
	return { titles: await loadTitles(fetch) };
};

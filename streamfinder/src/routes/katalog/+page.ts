import type { PageLoad } from './$types';
import { loadTitles } from '$lib/data/titles';

/**
 * Deliberately does NOT read url.searchParams — that is what stopped this page from
 * prerendering. The component reads the query string from page.url instead; see
 * $lib/filter-params for why that is the right place and not merely a workaround.
 */
export const load: PageLoad = async ({ parent, fetch }) => {
	const [{ dimensions }, titles] = await Promise.all([parent(), loadTitles(fetch)]);
	return { titles, dimensions };
};

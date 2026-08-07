import type { PageLoad } from './$types';
import { loadTitles } from '$lib/data/titles';

export const load: PageLoad = async ({ parent, fetch }) => {
	const [{ dimensions }, titles] = await Promise.all([parent(), loadTitles(fetch)]);
	return { titles, dimensions };
};

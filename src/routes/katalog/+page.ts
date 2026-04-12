import type { PageLoad } from './$types';

export const load: PageLoad = async ({ parent, url }) => {
	const { titles, dimensions } = await parent();
	// URL params for initial filter state (e.g. ?genre=Drama)
	const genre = url.searchParams.get('genre');
	return { titles, dimensions, initialGenre: genre };
};

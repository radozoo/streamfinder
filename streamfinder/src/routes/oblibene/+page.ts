import type { PageLoad } from './$types';

// The list itself lives in localStorage, so there is nothing to load per visitor —
// only the catalog, which the layout already has.
export const load: PageLoad = async ({ parent }) => {
	const { titles } = await parent();
	return { titles };
};

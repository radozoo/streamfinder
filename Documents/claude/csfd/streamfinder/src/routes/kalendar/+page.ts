import type { PageLoad } from './$types';

export const load: PageLoad = async ({ parent, url }) => {
	const { titles, dimensions } = await parent();
	// Guard against Number('') === 0 edge case when ?days= is present but empty
	const raw = url.searchParams.get('days');
	const initialDays = raw ? Math.min(Math.max(Number(raw), 28), 365) : 28;
	return {
		titles,
		dimensions,
		initialDays,
		initialPlatform: url.searchParams.get('platform') ?? '',
		initialType:     url.searchParams.get('type')     ?? '',
		initialGenre:    url.searchParams.get('genre')    ?? '',
	};
};

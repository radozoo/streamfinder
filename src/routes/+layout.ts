import type { LayoutLoad } from './$types';
import type { TitleIndex, Dimensions } from '$lib/types';
import { base } from '$app/paths';

export const prerender = true;

export const load: LayoutLoad = async ({ fetch }) => {
	const [indexRes, dimsRes] = await Promise.all([
		fetch(`${base}/data/titles_index.json`),
		fetch(`${base}/data/dimensions.json`),
	]);
	const titles: TitleIndex[] = await indexRes.json();
	const dimensions: Dimensions = await dimsRes.json();

	// Find latest vod_date for footer "last updated"
	const lastUpdate = titles.reduce((latest, t) => {
		if (t.vod_date && t.vod_date > latest) return t.vod_date;
		return latest;
	}, '');

	return { titles, dimensions, lastUpdate };
};

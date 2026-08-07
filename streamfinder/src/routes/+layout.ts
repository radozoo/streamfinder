import type { LayoutLoad } from './$types';
import type { Dimensions, SiteMeta } from '$lib/types';
import { base } from '$app/paths';

export const prerender = true;

/**
 * Deliberately small. This runs for every route, so anything fetched here is paid
 * for by every visitor — including someone opening a single title page, which is
 * what most shared links are.
 *
 * It used to fetch titles_index.json (6.3 MB gzipped) and scan all 51k entries for
 * one date to print in the footer. That date is now precomputed in meta.json (94
 * bytes). Routes that browse the catalog load the index themselves via
 * $lib/data/titles.
 */
export const load: LayoutLoad = async ({ fetch }) => {
	const [dimsRes, metaRes] = await Promise.all([
		fetch(`${base}/data/dimensions.json`),
		fetch(`${base}/data/meta.json`)
	]);
	const dimensions: Dimensions = await dimsRes.json();
	const meta: SiteMeta = await metaRes.json();

	return { dimensions, meta, lastUpdate: meta.last_vod_date };
};

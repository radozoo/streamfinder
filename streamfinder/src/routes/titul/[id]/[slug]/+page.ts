import type { PageLoad } from './$types';
import type { TitleDetail } from '$lib/types';
import { base } from '$app/paths';
import { error } from '@sveltejs/kit';

// Do not prerender individual title pages — served via SPA fallback (404.html)
export const prerender = false;

export const load: PageLoad = async ({ params, fetch }) => {
	const res = await fetch(`${base}/data/detail/${params.id}-${params.slug}.json`);
	if (!res.ok) error(404, 'Titul nenalezen');
	const title: TitleDetail = await res.json();
	return { title };
};

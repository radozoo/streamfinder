import type { PageLoad } from './$types';
import type { TitleDetail } from '$lib/types';
import { base } from '$app/paths';
import { error } from '@sveltejs/kit';

export const load: PageLoad = async ({ params, fetch }) => {
	const res = await fetch(`${base}/data/titles_detail.json`);
	const detail: Record<string, TitleDetail> = await res.json();
	const key = `${params.id}-${params.slug}`;
	const title = detail[key];
	if (!title) error(404, 'Titul nenalezen');
	return { title };
};

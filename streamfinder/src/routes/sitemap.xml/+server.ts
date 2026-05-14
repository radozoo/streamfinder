import { base } from '$app/paths';
import type { TitleIndex } from '$lib/types';

export const prerender = true;

export async function GET({ fetch, url }): Promise<Response> {
	const res = await fetch(`${base}/data/titles_index.json`);
	const titles: TitleIndex[] = await res.json();

	const origin = url.origin;
	const bp = base; // '' or '/csfd' etc.

	const staticPaths = ['/', '/katalog', '/kalendar', '/insights'];
	const titlePaths = titles.map((t) => `/titul/${t.id}/${t.slug}`);

	const allPaths = [...staticPaths, ...titlePaths];

	const xml = `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
${allPaths.map((p) => `  <url>\n    <loc>${origin}${bp}${p}</loc>\n  </url>`).join('\n')}
</urlset>`;

	return new Response(xml, {
		headers: {
			'Content-Type': 'application/xml; charset=utf-8',
			'Cache-Control': 'public, max-age=3600'
		}
	});
}

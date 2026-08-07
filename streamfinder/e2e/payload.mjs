/**
 * What each route actually downloads.
 *
 * The catalog index is 51k entries. It used to be fetched by the root layout, so
 * every route paid for it — including a single title page, which reads its own
 * detail shard and needs not one field of the index. Most shared links are title
 * pages, so that was the common case, not the edge case.
 *
 * This is a budget, not a benchmark. It fails when a route starts fetching data it
 * has no use for, which is how the regression happens: someone needs `titles` in a
 * component, adds it back to the layout's load because that is the easy place, and
 * every page silently gets multi-megabyte again. Nothing else would notice —
 * the site still works, just slower for everyone.
 *
 * Budgets are deliberately loose. They exist to catch a category change (a route
 * starts pulling the whole catalog), not to police a few kilobytes of growth.
 *
 * Run:  npm run test:payload
 */
import { chromium } from 'playwright';
import { startStaticServer } from './server.mjs';
import { pickShapes } from './shapes.mjs';

const failures = [];
const check = (ok, what, detail) => {
	console.log(`  ${ok ? 'ok  ' : 'FAIL'}: ${what}${detail ? ` — ${detail}` : ''}`);
	if (!ok) failures.push(what);
};

// Built site served the way GitHub Pages serves it — see startStaticServer for
// why neither `vite dev` nor `vite preview` can measure this honestly.
console.log('building…');
const { origin: ORIGIN, stop: stopServer } = await startStaticServer();
const browser = await chromium.launch();

const shape = pickShapes()[0];

// [label, path, may it fetch the index?, budget in KB for all data/*.json]
const ROUTES = [
	['detail', `/titul/${shape.id}/${shape.slug}`, false, 400],
	['oblibene', '/oblibene', true, 40_000],
	['katalog', '/katalog', true, 40_000],
	['home', '/', true, 40_000]
];

for (const [label, path, mayLoadIndex, budgetKb] of ROUTES) {
	// A fresh context per route: a shared one would carry the HTTP cache and the
	// module-level cache in $lib/data/titles, and a route would look innocent only
	// because an earlier route had already paid.
	const context = await browser.newContext();
	const page = await context.newPage();

	// Match the exported JSON only. An earlier version matched any URL containing
	// "/data/", which also caught the dev server's own /src/lib/data/titles.ts — so
	// Katalóg's 31 MB index was reported as "4 KB" and every budget passed while
	// measuring nothing.
	const isExportedData = (url) => /\/data\/[^?]*\.json(\?|$)/.test(url);
	const fetched = new Map();
	page.on('requestfinished', async (req) => {
		if (!isExportedData(req.url())) return;
		try {
			const { responseBodySize } = await req.sizes();
			fetched.set(req.url().split('/data/')[1], responseBodySize);
		} catch {
			/* aborted — nothing to weigh */
		}
	});

	try {
		await page.goto(ORIGIN + path, { waitUntil: 'domcontentloaded' });
		await page.waitForSelector('h1', { timeout: 60_000 });
		// networkidle, not a fixed wait: the index is tens of megabytes, and a short
		// sleep would let a route look cheap merely because its download had not
		// finished yet.
		await page.waitForLoadState('networkidle', { timeout: 90_000 }).catch(() => {});
		await page.waitForTimeout(1000);

		const total = [...fetched.values()].reduce((a, b) => a + b, 0) / 1024;
		const gotIndex = [...fetched.keys()].some((f) => f.startsWith('titles_index'));
		const files = [...fetched.entries()]
			.map(([f, b]) => `${f.split('/')[0]} ${Math.round(b / 1024)}k`)
			.join(', ');

		if (!mayLoadIndex) {
			check(!gotIndex, `${label}: does not download the catalog index`, files || 'no data files');
		}
		check(total < budgetKb, `${label}: under its ${budgetKb} KB data budget`,
			`${Math.round(total)} KB (${files || 'none'})`);
	} catch (e) {
		check(false, `${label}: loaded`, String(e).split('\n')[0]);
	} finally {
		await context.close();
	}
}

// The index still has to arrive when it is genuinely needed, or this "saving" is
// just a broken catalog.
const context = await browser.newContext();
const page = await context.newPage();
let indexFetched = false;
page.on('response', (r) => {
	if (r.url().includes('titles_index')) indexFetched = true;
});
try {
	await page.goto(`${ORIGIN}/katalog`, { waitUntil: 'domcontentloaded' });
	await page.waitForSelector('a.poster-link', { timeout: 60_000 });
	await page.waitForTimeout(1500);
	const cards = await page.locator('a.poster-link').count();
	check(indexFetched && cards > 0, 'katalog still gets the index and renders',
		`${cards} cards`);
} catch (e) {
	check(false, 'katalog renders', String(e).split('\n')[0]);
} finally {
	await context.close();
}

await browser.close();
stopServer();

console.log(failures.length ? `\nFAILED (${failures.length})` : '\nALL PAYLOAD CHECKS PASSED');
process.exit(failures.length ? 1 : 0);

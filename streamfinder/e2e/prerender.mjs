/**
 * Katalóg and Kalendář must be real pages, and their filters must survive a link.
 *
 * These two things pulled in opposite directions until the parsing moved out of
 * `load`, and the history here is worth keeping:
 *
 *   Reading url.searchParams inside load() makes prerendering fail — SvelteKit
 *   refuses, because one prerendered file cannot depend on a query string. The
 *   failure was a 500 that handleHttpError downgraded to a warning, so the build
 *   stayed green while both pages fell out of the build and were served as
 *   404.html. The site's two main pages answered crawlers with HTTP 404.
 *
 *   The obvious fix — swallow the throw so prerendering succeeds — would have been
 *   worse: the page would prerender with empty filters baked in, and a shared
 *   ?q=batman link would open the unfiltered catalog. Filters worked *because*
 *   prerendering was broken.
 *
 * Both properties are asserted here so neither can be traded for the other. Run
 * against the built site served like Pages, because prerendered pages take a
 * different path than the dev server's SSR.
 *
 * Run:  npm run test:prerender
 */
import { chromium } from 'playwright';
import { startStaticServer } from './server.mjs';

const failures = [];
const check = (ok, what, detail) => {
	console.log(`  ${ok ? 'ok  ' : 'FAIL'}: ${what}${detail ? ` — ${detail}` : ''}`);
	if (!ok) failures.push(what);
};

console.log('building…');
const { origin: ORIGIN, stop: stopServer } = await startStaticServer();
const browser = await chromium.launch();

// 1. Real files, real status codes. A crawler that gets 404 does not index the page.
for (const route of ['/katalog', '/kalendar']) {
	const res = await fetch(ORIGIN + route);
	const html = await res.text();
	check(res.status === 200, `${route} is a prerendered page, not the 404 fallback`,
		`HTTP ${res.status}`);
	// A 200 from the fallback would still be wrong: assert the page's own content is
	// in the HTML, not just that something answered.
	check(/Katalog|Kalendář VOD/.test(html), `${route} ships its content in the HTML`,
		`${html.length} bytes`);
}

// 2. A shared filtered link still opens filtered — the property the naive fix loses.
const page = await browser.newPage();
await page.setViewportSize({ width: 1440, height: 900 });
const errors = [];
page.on('pageerror', (e) => errors.push(String(e).split('\n')[0]));

for (const [route, sel] of [['katalog', '.result-count'], ['kalendar', null]]) {
	try {
		await page.goto(`${ORIGIN}/${route}`, { waitUntil: 'domcontentloaded' });
		await page.waitForSelector('a.poster-link', { timeout: 45_000 });
		await page.waitForTimeout(1200);
		const all = await page.locator('a.poster-link').count();

		await page.goto(`${ORIGIN}/${route}?q=batman`, { waitUntil: 'domcontentloaded' });
		await page.waitForSelector('a.poster-link', { timeout: 45_000 });
		await page.waitForTimeout(1500);
		const filtered = await page.locator('a.poster-link').count();

		check(filtered < all, `${route}: a shared ?q= link opens filtered`, `${all} → ${filtered}`);
		check((await page.locator('input').first().inputValue()) === 'batman',
			`${route}: the search box shows the shared query`);
		if (sel) {
			const shown = await page.locator(sel).innerText();
			check(/\d/.test(shown), `${route}: the result count rendered`, shown.trim());
		}

		// 3. Back still works. This area broke twice before — once because a native
		// history.replaceState wiped the router's state, once because replaceState()
		// from $app/navigation stores page.url.href rather than the URL it is given.
		await page.locator('a.poster-link').first().click();
		await page.waitForURL(/\/titul\//, { timeout: 45_000 });
		await page.waitForTimeout(500);
		await page.goBack();
		await page.waitForSelector('a.poster-link', { timeout: 45_000 });
		await page.waitForTimeout(1200);
		check(page.url().includes('q=batman'), `${route}: Back returns to the filtered URL`,
			page.url().replace(ORIGIN, ''));
		check((await page.locator('a.poster-link').count()) === filtered,
			`${route}: Back restores the filtered grid`);
	} catch (e) {
		check(false, `${route}: flow completed`, String(e).split('\n')[0]);
	}
}

check(errors.length === 0, 'no uncaught errors', errors.join(' | ') || 'none');

await browser.close();
stopServer();

console.log(failures.length ? `\nFAILED (${failures.length})` : '\nALL PRERENDER CHECKS PASSED');
process.exit(failures.length ? 1 : 0);

/**
 * End-to-end check of URL state and the Back button.
 *
 * This exists because the same area broke twice in a row, and neither break was
 * visible to anything else we run. Both type-checked, both built, and in one of them
 * the address bar was even correct — what was wrong lived in `history.state`, and
 * only showed up when a real user pressed a real Back button.
 *
 *   1. history.replaceState(null, ...) wiped the router's own history state, so Back
 *      updated the URL and never navigated.
 *   2. replaceState() from $app/navigation is a shallow-routing API: it stores
 *      `page.url.href` as the entry's URL rather than the one it is given, so the
 *      filtered URL was shown but never recorded, and Back restored an unfiltered
 *      page.
 *
 * Starts its own dev server so it can be run with a single command.
 *
 *   node e2e/url-state.mjs          (or: npm run test:e2e)
 */
import { spawn } from 'node:child_process';
import { chromium } from 'playwright';

const PORT = 5177;
const ORIGIN = `http://localhost:${PORT}`;
const PAGES = ['katalog', 'kalendar'];
const QUERY = 'batman';

const failures = [];
const check = (ok, what, detail) => {
	console.log(`  ${ok ? 'ok  ' : 'FAIL'}: ${what}${detail ? ` — ${detail}` : ''}`);
	if (!ok) failures.push(what);
};

const server = spawn('npx', ['vite', 'dev', '--port', String(PORT)], { stdio: 'ignore' });
const stop = () => server.kill();
process.on('exit', stop);

async function waitForServer() {
	for (let i = 0; i < 60; i++) {
		try {
			if ((await fetch(ORIGIN)).ok) return true;
		} catch {
			/* not up yet */
		}
		await new Promise((r) => setTimeout(r, 500));
	}
	throw new Error(`dev server did not start on ${PORT}`);
}

await waitForServer();
const browser = await chromium.launch();
const page = await browser.newPage();
await page.setViewportSize({ width: 1440, height: 900 });

const errors = [];
page.on('pageerror', (e) => errors.push(String(e)));

for (const route of PAGES) {
	console.log(`\n/${route}`);
	try {
		await runRoute(route);
	} catch (e) {
		// A broken Back button shows up as a timeout waiting for the grid. Reported as
		// a failure rather than an uncaught crash, which would take the summary — and
		// the dev server's shutdown — down with it.
		check(false, `${route}: flow completed`, String(e).split('\n')[0]);
	}
}

async function runRoute(route) {
	await page.goto(`${ORIGIN}/${route}`, { waitUntil: 'domcontentloaded' });
	await page.waitForSelector('a.poster-card');
	const unfiltered = await page.locator('a.poster-card').count();

	// Filtering must reach the URL — if it does not, there is nothing for Back to
	// restore, and the failure is silent because the page itself looks right.
	await page.locator('input').first().fill(QUERY);
	await page.waitForTimeout(900);
	const filtered = await page.locator('a.poster-card').count();
	check(page.url().includes(`q=${QUERY}`), `${route}: filter reaches the URL`, page.url());
	check(filtered < unfiltered, `${route}: filter actually narrows the grid`, `${unfiltered} → ${filtered}`);

	await page.locator('a.poster-card').first().click();
	await page.waitForURL(/\/titul\//);
	await page.waitForTimeout(400);

	await page.goBack();
	await page.waitForSelector('a.poster-card', { timeout: 15_000 });
	await page.waitForTimeout(800);

	// The page must come back, not just the address bar: assert on rendered cards.
	check(page.url().includes(`q=${QUERY}`), `${route}: Back returns to the filtered URL`, page.url());
	check(
		(await page.locator('input').first().inputValue()) === QUERY,
		`${route}: Back restores the filter input`
	);
	check(
		(await page.locator('a.poster-card').count()) === filtered,
		`${route}: Back restores the filtered grid`
	);
	check((await page.locator('h1.detail-title').count()) === 0, `${route}: Back leaves the detail page`);
}

check(errors.length === 0, 'no uncaught errors', errors.join(' | ') || 'none');

await browser.close();
stop();

console.log(failures.length ? `\nFAILED (${failures.length})` : '\nALL URL-STATE CHECKS PASSED');
process.exit(failures.length ? 1 : 0);

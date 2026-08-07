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
import { chromium } from 'playwright';
import { startDevServer } from './server.mjs';

const PAGES = ['katalog', 'kalendar'];
const QUERY = 'batman';

const failures = [];
const check = (ok, what, detail) => {
	console.log(`  ${ok ? 'ok  ' : 'FAIL'}: ${what}${detail ? ` — ${detail}` : ''}`);
	if (!ok) failures.push(what);
};

// The server picks its own free port; using its origin keeps this run off
// whatever else happens to be listening on this machine.
const { origin: ORIGIN, stop: stopServer } = await startDevServer();
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
	await page.waitForSelector('a.poster-link');
	const unfiltered = await page.locator('a.poster-link').count();

	// Filtering must reach the URL — if it does not, there is nothing for Back to
	// restore, and the failure is silent because the page itself looks right.
	await page.locator('input').first().fill(QUERY);
	await page.waitForTimeout(900);
	const filtered = await page.locator('a.poster-link').count();
	check(page.url().includes(`q=${QUERY}`), `${route}: filter reaches the URL`, page.url());
	check(filtered < unfiltered, `${route}: filter actually narrows the grid`, `${unfiltered} → ${filtered}`);

	await page.locator('a.poster-link').first().click();
	await page.waitForURL(/\/titul\//);
	await page.waitForTimeout(400);

	await page.goBack();
	await page.waitForSelector('a.poster-link', { timeout: 15_000 });
	await page.waitForTimeout(800);

	// The page must come back, not just the address bar: assert on rendered cards.
	check(page.url().includes(`q=${QUERY}`), `${route}: Back returns to the filtered URL`, page.url());
	check(
		(await page.locator('input').first().inputValue()) === QUERY,
		`${route}: Back restores the filter input`
	);
	check(
		(await page.locator('a.poster-link').count()) === filtered,
		`${route}: Back restores the filtered grid`
	);
	check((await page.locator('h1.detail-title').count()) === 0, `${route}: Back leaves the detail page`);
}

// ── Multi-select facets ───────────────────────────────────────────────────────
// A facet that accepts several values is only usable if the dropdown survives the
// first pick. It did not: the panel is rendered as a DOM sibling of the dropdown, so
// clicking a pill moved focus "outside" and closed it, and every multi-select facet
// behaved as single-select unless you reopened it each time.
console.log('\nmulti-select facets');

async function openPanel(label) {
	const trigger = page.locator('button.filter-trigger').filter({ hasText: label }).first();
	for (let i = 0; i < 4; i++) {
		if ((await trigger.getAttribute('aria-expanded')) === 'true') return true;
		await trigger.click();
		await page.waitForTimeout(350);
	}
	return false;
}

// Click without moving the pointer out of the panel, the way a person does.
async function clickPill(i) {
	const box = await page.locator('.filter-panel button.pill').nth(i).boundingBox();
	await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
	await page.mouse.down();
	await page.mouse.up();
	await page.waitForTimeout(800);
}

for (const [route, label, param] of [
	['katalog', 'Typ', 'type'],
	['katalog', 'Žánr', 'genre'],
	['kalendar', 'Typ', 'type']
]) {
	try {
		await page.goto(`${ORIGIN}/${route}`, { waitUntil: 'domcontentloaded' });
		await page.waitForSelector('a.poster-link');
		await page.waitForTimeout(600);
		await openPanel(label);
		await clickPill(0);
		const stillOpen = (await page.locator('.filter-panel button.pill').count()) > 0;
		check(stillOpen, `${route}/${label}: panel stays open after the first pick`);
		if (!stillOpen) continue;
		await clickPill(1);
		const url = decodeURIComponent(page.url());
		check(
			(url.match(new RegExp(`${param}=([^&]*)`))?.[1] ?? '').includes(','),
			`${route}/${label}: two values reach the URL`,
			url.replace(ORIGIN, '')
		);
		check(
			(await page.locator('.filter-panel button.pill.active').count()) === 2,
			`${route}/${label}: both pills read as selected`
		);
	} catch (e) {
		check(false, `${route}/${label}: multi-select flow completed`, String(e).split('\n')[0]);
	}
}


// ── Favourites ────────────────────────────────────────────────────────────────
// Stored in localStorage under a ČSFD id rather than the catalog's local SERIAL id,
// so a database rebuild cannot repoint someone's list at different films. These
// check the parts that would silently lose a list: persistence across a reload, and
// that the heart on a card does not follow the card's link.
console.log('\nfavourites');
try {
	await page.goto(`${ORIGIN}/katalog`, { waitUntil: 'domcontentloaded' });
	await page.waitForSelector('.poster-card');
	await page.waitForTimeout(600);

	const urlBefore = page.url();
	await page.locator('.fav-btn.card').nth(0).click();
	await page.waitForTimeout(250);
	await page.locator('.fav-btn.card').nth(1).click();
	await page.waitForTimeout(400);

	check(page.url() === urlBefore, 'hearting a card does not navigate', page.url().replace(ORIGIN, ''));
	check((await page.locator('.fav-btn.on').count()) === 2, 'both hearts read as on');
	check(
		(await page.locator('.nav-count').innerText().catch(() => '')) === '2',
		'the nav badge counts them'
	);

	const stored = await page.evaluate(() => localStorage.getItem('streamfinder:favorites:v1'));
	check(JSON.parse(stored ?? '{}').ids?.length === 2, 'two ids are persisted', stored ?? 'nothing');

	await page.goto(`${ORIGIN}/oblibene`, { waitUntil: 'domcontentloaded' });
	await page.waitForTimeout(700);
	check((await page.locator('.poster-card').count()) === 2, 'the Oblíbené page lists them');

	await page.reload({ waitUntil: 'domcontentloaded' });
	await page.waitForTimeout(700);
	check((await page.locator('.poster-card').count()) === 2, 'they survive a reload');

	await page.locator('.fav-btn.card').first().click();
	await page.waitForTimeout(500);
	check((await page.locator('.poster-card').count()) === 1, 'un-hearting removes it from the list');

	await page.goto(`${ORIGIN}/katalog`, { waitUntil: 'domcontentloaded' });
	await page.waitForSelector('.poster-card');
	await page.waitForTimeout(600);
	const all = await page.locator('.poster-card').count();
	await page.locator('button.fav-filter').click();
	await page.waitForTimeout(900);
	const only = await page.locator('.poster-card').count();
	check(only === 1 && only < all, 'the "Oblíbené" filter narrows to the saved ones', `${all} → ${only}`);
	check(page.url().includes('fav=1'), 'the filter reaches the URL', page.url().replace(ORIGIN, ''));
} catch (e) {
	check(false, 'favourites flow completed', String(e).split('\n')[0]);
}

// ── Kalendář: the "Připravované" section survives Back ────────────────────────
// It was the one piece of state on that page held only in the component, so a
// navigation destroyed it. Opening it, reading an upcoming title and pressing Back
// collapsed the section — and because the page then lost ~8,000px of content, the
// restored scroll position landed weeks earlier in the past. The visitor's own words:
// "vrátim sa na tituly o mesiac spätky".
console.log('\nKalendář: Připravované');

try {
	await page.goto(`${ORIGIN}/kalendar`, { waitUntil: 'domcontentloaded' });
	await page.waitForSelector('.upcoming-toggle');
	// The toggle is in the server-rendered HTML before its handler exists; clicking a
	// button that is present but not yet hydrated does nothing at all.
	await page.waitForTimeout(1500);
	await page.locator('.upcoming-toggle').click();
	await page.waitForTimeout(2200); // the reveal scroll is smooth; let it settle

	const openY = await page.evaluate(() => Math.round(window.scrollY));
	const blocks = await page.locator('.day-block.is-upcoming').count();
	check(page.url().includes('upcoming=1'), 'opening the section reaches the URL', page.url().replace(ORIGIN, ''));
	check(blocks > 0, 'the section renders upcoming days', `${blocks} day(s)`);
	check(openY > 500, 'opening reveals the nearest upcoming day rather than the far end', `scrollY ${openY}`);

	// Click a link that is already on screen. Clicking one that is not makes the
	// browser scroll to it first, which is then the position Back restores — the
	// mistake that made this look like a scroll-restoration bug when it is not.
	const link = await page.evaluateHandle(() =>
		[...document.querySelectorAll('.day-block.is-upcoming a[href*="/titul/"]')].find((a) => {
			const r = a.getBoundingClientRect();
			return r.top > 80 && r.bottom < window.innerHeight - 80;
		}) ?? null
	);
	await link.asElement().click();
	await page.waitForURL(/\/titul\//);
	await page.waitForTimeout(500);

	await page.goBack();
	await page.waitForSelector('.upcoming-toggle', { timeout: 15_000 });
	await page.waitForTimeout(1200);

	check((await page.locator('.upcoming-toggle.open').count()) === 1, 'Back leaves the section open');
	check((await page.locator('.day-block.is-upcoming').count()) === blocks, 'Back restores every upcoming day');
	const backY = await page.evaluate(() => Math.round(window.scrollY));
	check(Math.abs(backY - openY) < 150, 'Back restores the scroll position', `${openY} → ${backY}`);

	// A shared link has to arrive in the same state.
	await page.goto(`${ORIGIN}/kalendar?upcoming=1`, { waitUntil: 'domcontentloaded' });
	await page.waitForSelector('.upcoming-toggle');
	await page.waitForTimeout(1500);
	check((await page.locator('.upcoming-toggle.open').count()) === 1, 'a shared ?upcoming=1 link opens the section');
} catch (e) {
	check(false, 'Připravované flow completed', String(e).split('\n')[0]);
}

check(errors.length === 0, 'no uncaught errors', errors.join(' | ') || 'none');

await browser.close();
stopServer();

console.log(failures.length ? `\nFAILED (${failures.length})` : '\nALL URL-STATE CHECKS PASSED');
process.exit(failures.length ? 1 : 0);

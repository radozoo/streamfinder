/**
 * The footer's "last updated" has to be true, and it has to be the same string
 * everywhere.
 *
 * It used to print `last_vod_date` — the newest release date in the catalog, which
 * includes titles that have not come out yet. On 7 August the site therefore claimed
 * it had last been updated on 31 August. The number was real; the label was wrong.
 * It now prints `last_refresh_at`, which only an `update` run that actually fetched
 * from ČSFD writes.
 *
 * The second property is subtler. Every page here is prerendered, so this string is
 * baked in CI (UTC) and produced again during hydration in the visitor's browser
 * (their zone). Without an explicit timeZone the two disagree — a hydration mismatch
 * that shows up as the time silently changing a moment after the page loads. That is
 * exactly the kind of thing a later edit removes without noticing, so it is asserted
 * from three zones rather than trusted.
 *
 * Run:  npm run test:freshness
 */
import { chromium } from 'playwright';
import { startStaticServer } from './server.mjs';
import { readFileSync } from 'node:fs';

const meta = JSON.parse(readFileSync(new URL('../static/data/meta.json', import.meta.url), 'utf-8'));
const { origin, stop } = await startStaticServer();
const browser = await chromium.launch();

// What the footer must say, derived from the data rather than hard-coded — the test
// travels with the catalog instead of needing an edit after every refresh.
const expected = meta.last_refresh_at
	? new Date(meta.last_refresh_at).toLocaleString('cs-CZ', {
			day: 'numeric', month: 'long', year: 'numeric',
			hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Prague'
		})
	: null;

let failures = 0;
const fail = (msg) => { failures++; console.log(`  FAIL ${msg}`); };

if (!expected) {
	fail('meta.json carries no last_refresh_at — run `csfd update` before this test');
} else if (meta.last_refresh_at === meta.last_vod_date) {
	fail('last_refresh_at equals last_vod_date — the old bug is back');
}

for (const timezoneId of ['Europe/Prague', 'America/New_York', 'Asia/Tokyo']) {
	const ctx = await browser.newContext({ timezoneId, locale: 'cs-CZ' });
	const page = await ctx.newPage();
	const consoleErrors = [];
	page.on('console', (m) => { if (m.type() === 'error') consoleErrors.push(m.text()); });

	for (const path of ['/', '/katalog', '/kalendar']) {
		await page.goto(origin + path, { waitUntil: 'load' });
		const sel = '.footer-update';
		const baked = (await page.textContent(sel).catch(() => null))?.replace(/\s+/g, ' ').trim();
		await page.waitForTimeout(800); // hydration
		const hydrated = (await page.textContent(sel).catch(() => null))?.replace(/\s+/g, ' ').trim();

		if (!baked) fail(`${timezoneId} ${path}: no footer timestamp rendered`);
		else if (baked !== hydrated) fail(`${timezoneId} ${path}: hydration changed it\n    baked    ${baked}\n    hydrated ${hydrated}`);
		else if (!hydrated.includes(expected)) fail(`${timezoneId} ${path}: expected "${expected}", got "${hydrated}"`);
		else console.log(`  ok  ${timezoneId.padEnd(17)} ${path.padEnd(10)} ${hydrated}`);
	}
	if (consoleErrors.length) fail(`${timezoneId}: console errors ${JSON.stringify(consoleErrors.slice(0, 2))}`);
	await ctx.close();
}

await browser.close();
stop();
console.log(failures ? `\nFAILED — ${failures} problem(s)` : '\nFOOTER FRESHNESS OK');
process.exit(failures ? 1 : 0);

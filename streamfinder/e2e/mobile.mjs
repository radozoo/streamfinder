/**
 * The filters have to be reachable on a phone.
 *
 * `FilterBar` is a row of dropdowns that cannot fit a narrow screen, so it is
 * display:none under 640px. Katalog paired that with a floating button and a bottom
 * sheet; Kalendář never had one, so on a phone its filters were not merely awkward —
 * there was no way to open them at all, and nothing on the page said so. It looked
 * like a design choice rather than a hole.
 *
 * Two things about testing this, both learned the hard way:
 *
 *   The FAB is tapped with page.touchscreen.tap, not locator.click(). Playwright's
 *   actionability check reports a poster card "intercepts pointer events" over a
 *   position:fixed element under mobile emulation, and refuses. That disagreement is
 *   Playwright's: document.elementFromPoint at the same coordinates returns the FAB,
 *   a real tap opens the sheet, and the deployed pre-change site behaves identically.
 *   So the hit test is asserted explicitly, and the tap goes through the browser's
 *   own input pipeline.
 *
 *   The assertions run against the built site, because the sheet only exists below a
 *   breakpoint and the point is what a visitor actually gets.
 *
 * Run:  npm run test:mobile
 */
import { chromium, devices } from 'playwright';
import { startStaticServer } from './server.mjs';

const { origin, stop } = await startStaticServer();
const browser = await chromium.launch();

const failures = [];
const check = (ok, what, detail) => {
	console.log(`  ${ok ? 'ok  ' : 'FAIL'}: ${what}${detail ? ` — ${detail}` : ''}`);
	if (!ok) failures.push(what);
};

// Katalog filters by "added to VOD" window; Kalendář's whole axis is the date, so it
// has no such group. Everything else must be the same on both.
const SHARED_GROUPS = ['Typ', 'Platforma', 'Žánr', 'Tagy', 'Tvůrci', 'Rok výroby', 'Min. hodnocení'];

for (const [label, path, extraGroups] of [
	['katalog', '/katalog', ['Přidáno na VOD']],
	['kalendar', '/kalendar', []]
]) {
	console.log(`\n${label} @ iPhone 13`);
	const ctx = await browser.newContext({ ...devices['iPhone 13'] });
	const page = await ctx.newPage();
	try {
		await page.goto(origin + path, { waitUntil: 'load' });
		await page.waitForTimeout(2000);

		check(!(await page.locator('.filter-bar').isVisible()), `${label}: the desktop filter row is hidden`);

		const fab = page.locator('.filter-fab');
		check((await fab.count()) === 1 && (await fab.isVisible()), `${label}: the filter button is on screen`);

		const box = await fab.boundingBox();
		const x = box.x + box.width / 2;
		const y = box.y + box.height / 2;
		const onTop = await page.evaluate(([x, y]) => document.elementFromPoint(x, y)?.className ?? '', [x, y]);
		check(onTop.includes('filter-fab'), `${label}: nothing covers the filter button`, onTop || 'nothing there');

		await page.touchscreen.tap(x, y);
		await page.waitForTimeout(800);
		check(await page.locator('.filter-sheet').isVisible(), `${label}: tapping it opens the sheet`);

		const groups = await page.locator('.filter-sheet .filter-label').allTextContents();
		const expected = [...extraGroups, ...SHARED_GROUPS];
		const missing = expected.filter((g) => !groups.includes(g));
		check(missing.length === 0, `${label}: the sheet offers every filter`, missing.length ? `missing ${missing.join(', ')}` : groups.join(' / '));
		// Kalendář must not grow a control that contradicts its own date axis.
		if (!extraGroups.includes('Přidáno na VOD')) {
			check(!groups.includes('Přidáno na VOD'), `${label}: no "Přidáno na VOD" group`);
		}

		// A filter picked in the sheet has to reach the URL, or nothing survives Back.
		const pill = page.locator('.filter-sheet .filter-group', { hasText: 'Platforma' }).locator('button').first();
		const picked = (await pill.textContent())?.trim().split('\n')[0];
		await pill.click();
		await page.waitForTimeout(900);
		check(page.url().includes('platform='), `${label}: a pick in the sheet reaches the URL`, new URL(page.url()).search || 'no query');

		// Tapped, not clicked, for the same reason as the FAB — it is fixed-position
		// chrome and Playwright's actionability check will not have it.
		const apply = await page.locator('.apply-btn').boundingBox();
		await page.touchscreen.tap(apply.x + apply.width / 2, apply.y + apply.height / 2);
		await page.waitForTimeout(600);
		check((await page.locator('.filter-sheet').count()) === 0, `${label}: the apply button closes the sheet`);
		check((await page.locator('.fab-badge').textContent().catch(() => null)) === '1',
			`${label}: the button shows how many filters are on`, `picked "${picked}"`);
	} catch (e) {
		check(false, `${label}: flow completed`, String(e).split('\n')[0]);
	}
	await ctx.close();
}

await browser.close();
stop();
console.log(failures.length ? `\nFAILED (${failures.length})` : '\nMOBILE FILTERS OK');
process.exit(failures.length ? 1 : 0);

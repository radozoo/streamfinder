/**
 * A filter panel has to close when the mouse walks away from it.
 *
 * `FilterDropdown` opens on hover and closed on a 150ms timer after mouseleave — but
 * only if it was not "pinned", and it pinned itself on `focusin`. Clicking a pill
 * focuses that pill, so every selection pinned the panel, and focus does not follow
 * the pointer: nothing ever released it. The panel sat over the page until you
 * clicked somewhere else entirely, which is what it was reported as.
 *
 * The flag existed for a real reason, so the fix cannot just delete it: someone
 * tabbing through the pills must not have the panel yanked away because the pointer
 * happens to rest elsewhere. Hence both halves are checked here — and so is
 * multi-select, because an earlier attempt at this same close-behaviour made every
 * facet single-select (selecting a pill counted as focus leaving, closing the panel
 * after one pick).
 *
 * Why an e2e script and not a component test: the whole bug lives in the difference
 * between a real pointer and a programmatic one. `element.click()` does not move
 * focus, so in jsdom or a synthetic click the bug does not even reproduce.
 *
 * Run:  npm run test:filters
 */
import { chromium } from 'playwright';
import { startDevServer } from './server.mjs';

const { origin, stop } = await startDevServer();
const browser = await chromium.launch();

const failures = [];
const check = (ok, what, detail) => {
	console.log(`  ${ok ? 'ok  ' : 'FAIL'}: ${what}${detail ? ` — ${detail}` : ''}`);
	if (!ok) failures.push(what);
};

const AWAY = [20, 870]; // far from any dropdown, still inside the viewport
const page = await (await browser.newContext({ viewport: { width: 1400, height: 900 } })).newPage();
const panels = () => page.locator('.filter-panel').count();
const trigger = () => page.locator('.filter-trigger', { hasText: 'Platforma' });

async function fresh() {
	await page.goto(`${origin}/kalendar`);
	await trigger().waitFor({ timeout: 20000 });
	await page.waitForTimeout(400); // hydration; before it the trigger has no handlers
}

try {
	// ── the reported bug ────────────────────────────────────────────────────────
	await fresh();
	await trigger().hover();
	await page.waitForTimeout(250);
	check((await panels()) === 1, 'hovering the trigger opens the panel');

	await page.locator('.filter-panel button').first().click();
	await page.waitForTimeout(150);
	check((await panels()) === 1, 'picking a value leaves the panel open for the next one');

	await page.mouse.move(...AWAY);
	await page.waitForTimeout(500);
	check((await panels()) === 0, 'moving the mouse away closes it, even after a pick');

	// ── multi-select must survive the fix ───────────────────────────────────────
	await fresh();
	await trigger().hover();
	await page.waitForTimeout(250);
	const pills = page.locator('.filter-panel button');
	for (const i of [0, 1, 2]) {
		await pills.nth(i).click();
		await page.waitForTimeout(120);
	}
	check((await panels()) === 1, 'three picks in one opening, panel still up');
	check((await trigger().locator('.filter-badge').textContent().catch(() => null)) === '3',
		'the trigger counts all three');
	check(page.url().includes('platform='), 'the picks reach the URL',
		decodeURIComponent(new URL(page.url()).search));

	// Moving WITHIN the panel is not leaving it.
	const box = await page.locator('.filter-panel').boundingBox();
	await page.mouse.move(box.x + box.width / 2, box.y + box.height - 8);
	await page.waitForTimeout(400);
	check((await panels()) === 1, 'moving inside the panel does not close it');

	await page.mouse.move(...AWAY);
	await page.waitForTimeout(500);
	check((await panels()) === 0, 'and leaving it does');
	check((await page.locator('.filter-badge').first().textContent().catch(() => null)) === '3',
		'closing keeps the selection');

	// ── the keyboard half, which the pin was there to protect ───────────────────
	await fresh();
	await trigger().focus();
	await page.keyboard.press('Enter');
	await page.waitForTimeout(250);
	check((await panels()) === 1, 'Enter on the trigger opens it');

	await page.keyboard.press('Tab'); // into the panel
	await page.waitForTimeout(150);
	await page.mouse.move(...AWAY);
	await page.waitForTimeout(500);
	check((await panels()) === 1, 'a pointer elsewhere does not close it under a keyboard user');

	await page.keyboard.press('Escape');
	await page.waitForTimeout(300);
	check((await panels()) === 0, 'Escape from inside the panel closes it');
	check(await trigger().evaluate((el) => el === document.activeElement),
		'Escape hands focus back to the trigger');
} catch (e) {
	check(false, 'flow completed', String(e).split('\n')[0]);
}

await browser.close();
stop();
console.log(failures.length ? `\nFAILED (${failures.length})` : '\nFILTER DROPDOWN OK');
process.exit(failures.length ? 1 : 0);

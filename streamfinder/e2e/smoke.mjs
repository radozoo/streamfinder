/**
 * Smoke sweep: open a real page for every awkward data shape and look for damage.
 *
 * The rendering bugs this project has shipped were never wrong logic — they were a
 * shape nobody opened. An episode named "21:00". A work with no genres. A cast of a
 * hundred and forty. Each looked fine on the titles a developer clicks.
 *
 * So this does not assert on specific titles. It picks the extremes out of the
 * exported catalog (see shapes.mjs), opens each one, and checks the things that are
 * true of EVERY page regardless of content:
 *
 *   - nothing throws
 *   - the page has a heading
 *   - no placeholder leaked into the text (undefined / NaN / [object Object])
 *   - every service button can actually be clicked somewhere
 *   - the body does not scroll sideways
 *   - a section that is rendered is not rendered empty
 *
 * Run:  npm run test:smoke
 */
import { chromium } from 'playwright';
import { startDevServer } from './server.mjs';
import { pickShapes } from './shapes.mjs';

const PORT = 5178;
const ORIGIN = `http://localhost:${PORT}`;

const failures = [];
const warnings = [];

const { stop: stopServer } = await startDevServer(PORT);


// Placeholders that mean a value was formatted without being checked. Matched with
// word boundaries so a film legitimately titled "Null" is not a finding.
const LEAKED = /\b(undefined|NaN|\[object Object\])\b/;

const shapes = pickShapes();
console.log(`sweeping ${shapes.length} shapes\n`);

const browser = await chromium.launch();
const page = await browser.newPage();
await page.setViewportSize({ width: 1280, height: 900 });

for (const t of shapes) {
	const problems = [];
	const errors = [];
	const onError = (e) => errors.push(String(e).split('\n')[0]);
	page.on('pageerror', onError);

	try {
		await page.goto(`${ORIGIN}/titul/${t.id}/${t.slug}`, { waitUntil: 'domcontentloaded' });
		await page.waitForSelector('h1.detail-title', { timeout: 10_000 });
		await page.waitForTimeout(250);

		const report = await page.evaluate(() => {
			const text = document.body.innerText;
			const vodLinks = [...document.querySelectorAll('.vod-actions a')];
			// A section counts as empty only when it has a heading and neither text NOR
			// embedded media under it. Text alone is not enough: the Trailer section is
			// a single <iframe>, which contributes no innerText, and the first version
			// of this check reported every trailer on the site as an empty section.
			const sections = [...document.querySelectorAll('section')].map((s) => ({
				heading: s.querySelector('h2')?.textContent?.trim() ?? '',
				body:
					s.innerText.replace(s.querySelector('h2')?.textContent ?? '', '').trim().length +
					s.querySelectorAll('iframe, img, video, svg, canvas').length
			}));
			return {
				heading: document.querySelector('h1.detail-title')?.textContent?.trim() ?? '',
				text,
				vodTotal: vodLinks.length,
				vodDead: vodLinks.filter((a) => !a.getAttribute('href')).length,
				overflow: document.documentElement.scrollWidth - window.innerWidth,
				emptySections: sections.filter((s) => s.heading && s.body === 0).map((s) => s.heading),
				brokenImages: [...document.images].filter((i) => i.complete && i.naturalWidth === 0).length
			};
		});

		if (!report.heading) problems.push('no heading');
		const leak = report.text.match(LEAKED);
		if (leak) problems.push(`leaked "${leak[0]}"`);
		if (report.vodDead) problems.push(`${report.vodDead}/${report.vodTotal} service buttons have no href`);
		if (report.overflow > 1) problems.push(`body scrolls sideways by ${report.overflow}px`);
		if (report.emptySections.length) problems.push(`empty section: ${report.emptySections.join(', ')}`);
		if (errors.length) problems.push(`error: ${errors[0]}`);
		// Remote artwork can fail for reasons that are not our bug — reported, not failed.
		if (report.brokenImages) warnings.push(`${t.shape}: ${report.brokenImages} image(s) did not load`);
	} catch (e) {
		problems.push(String(e).split('\n')[0]);
	} finally {
		page.off('pageerror', onError);
	}

	const label = `${t.shape} — ${t.title.slice(0, 34)}`;
	console.log(`  ${problems.length ? 'FAIL' : 'ok  '}: ${label}`);
	for (const p of problems) console.log(`        ${p}`);
	if (problems.length) failures.push(label);
}

await browser.close();
stopServer();

if (warnings.length) console.log(`\nwarnings (not failures):\n  ${warnings.join('\n  ')}`);
console.log(
	failures.length
		? `\nFAILED — ${failures.length}/${shapes.length} shapes`
		: `\nALL ${shapes.length} SHAPES OK`
);
process.exit(failures.length ? 1 : 0);

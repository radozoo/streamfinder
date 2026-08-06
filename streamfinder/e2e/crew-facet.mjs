/**
 * The crew facet, and the payload decision behind it.
 *
 * `crew_ids` used to sit on every entry in titles_index.json. It was 3.97 MB of that
 * file's 10.24 MB gzipped — integer soup is the one thing gzip cannot squeeze — and
 * every visitor paid it to power a facet most of them never open. It now lives in
 * crew_titles.json, fetched on demand.
 *
 * That split can regress in two directions, and neither shows up in a type check:
 *
 *   1. The data comes back inline (someone re-adds crew_ids to the index) and the
 *      saving quietly evaporates. Asserted by watching the network: a plain /katalog
 *      visit must NOT request crew_titles.json.
 *   2. The facet breaks, because the map now arrives after the first render. Landing
 *      on a shared ?crew=… link computes the grid before the fetch resolves, so the
 *      map has to be reactive state — with a plain `let` the filter is silently
 *      skipped and the visitor sees an unfiltered catalog.
 *
 * The expected result count is computed from the exported data rather than hardcoded,
 * so this keeps working after a refresh and asserts the real number, not just
 * "fewer than before".
 *
 * Run:  node e2e/crew-facet.mjs
 */
import { readFileSync } from 'node:fs';
import { chromium } from 'playwright';
import { startDevServer } from './server.mjs';

const DATA = new URL('../static/data/', import.meta.url);

const failures = [];
const check = (ok, what, detail) => {
	console.log(`  ${ok ? 'ok  ' : 'FAIL'}: ${what}${detail ? ` — ${detail}` : ''}`);
	if (!ok) failures.push(what);
};

const read = (f) => JSON.parse(readFileSync(new URL(f, DATA), 'utf8'));
const titles = read('titles_index.json');
const crew = read('crew_index.json');
const crewTitles = read('crew_titles.json');

check(!('crew_ids' in titles[0]), 'the index no longer carries crew_ids');

// Pick a person whose name is worth filtering by: enough top-level titles to prove the
// filter bit, few enough to stay under one page so the count is exact and stable.
const topLevel = new Set(titles.filter((t) => t.is_toplevel !== false).map((t) => t.id));
const byName = new Map();
for (const c of crew) {
	if (!byName.has(c.name)) byName.set(c.name, []);
	byName.get(c.name).push(c.id);
}
const countFor = (ids) => {
	const set = new Set(ids);
	return titles.filter((t) => topLevel.has(t.id) && (crewTitles[t.id] ?? []).some((i) => set.has(i)))
		.length;
};

let person = null;
for (const [name, ids] of byName) {
	// A name the URL and the autocomplete can both carry unambiguously.
	if (/[,&]/.test(name)) continue;
	const n = countFor(ids);
	if (n >= 6 && n <= 40) {
		person = { name, expected: n };
		break;
	}
}
if (!person) {
	console.log('FAIL: no suitable crew member found in the exported data');
	process.exit(1);
}
console.log(`filtering by "${person.name}" — ${person.expected} top-level titles expected\n`);

// The server picks its own free port; using its origin keeps this run off
// whatever else happens to be listening on this machine.
const { origin: ORIGIN, stop: stopServer, tail, died } = await startDevServer();
const browser = await chromium.launch();
const page = await browser.newPage();
await page.setViewportSize({ width: 1440, height: 900 });

const requested = [];
page.on('request', (r) => {
	if (r.url().includes('crew_titles.json')) requested.push(r.url());
});
const errors = [];
page.on('pageerror', (e) => errors.push(String(e).split('\n')[0]));

try {
	// 1. A plain visit must not pay for the facet.
	// The dev server compiles this route on first hit and the index is ~31 MB, so the
	// first paint is far slower here than in a built site. 60s, once.
	await page.goto(`${ORIGIN}/katalog`, { waitUntil: 'domcontentloaded' });
	await page.waitForSelector('a.poster-link', { timeout: 60_000 });
	await page.waitForTimeout(1500);
	const unfiltered = Number((await page.locator('.result-count').innerText()).replace(/\D/g, ''));
	check(requested.length === 0, 'a plain /katalog visit does not fetch crew_titles.json',
		requested.length ? requested.join(' ') : 'no request');
	check(unfiltered > 1000, 'the unfiltered catalog rendered', String(unfiltered));

	// 2. A shared crew link must apply, even though the map arrives after first render.
	await page.goto(`${ORIGIN}/katalog?crew=${encodeURIComponent(person.name)}`, {
		waitUntil: 'domcontentloaded'
	});
	await page.waitForSelector('a.poster-link');
	await page.waitForTimeout(2500);

	check(requested.length > 0, 'using the facet does fetch crew_titles.json');

	const filtered = Number((await page.locator('.result-count').innerText()).replace(/\D/g, ''));
	check(filtered === person.expected,
		'a shared ?crew= link filters to the exact expected count',
		`got ${filtered}, expected ${person.expected}`);
	check(filtered < unfiltered, 'the crew filter narrows the catalog', `${unfiltered} → ${filtered}`);
} catch (e) {
	// Always dump the server's output. We hold the `npx` wrapper, not vite itself, so
	// vite dying does not raise an exit event here — the only trace is its own log.
	const where = `at ${page.url()} (wrapper exit: ${died() ?? 'none'})\n--- dev server output ---\n${tail()}`;
	check(false, 'crew facet flow completed', `${String(e).split('\n')[0]} — ${where}`);
}

check(errors.length === 0, 'no uncaught errors', errors.join(' | ') || 'none');

await browser.close();
stopServer();

console.log(failures.length ? `\nFAILED (${failures.length})` : '\nALL CREW-FACET CHECKS PASSED');
process.exit(failures.length ? 1 : 0);

import { beforeEach, describe, expect, test } from 'vitest';
import { load } from './+page';
import type { TitleIndex } from '$lib/types';
import { __resetTitlesCache } from '$lib/data/titles';

/**
 * The landing-page rails, tested through the REAL load() function.
 *
 * `import type { PageLoad } from './$types'` is erased at runtime, so load()'s only
 * runtime dependencies are the `parent()` and `fetch` it is handed — stub those and
 * these tests exercise exactly the code the site runs. Re-implementing the selection
 * here would test a copy, which is how a rail drifts away from its guard without
 * anyone noticing.
 *
 * Every rule below is here because the carousel broke on it. Correcting votes_count
 * (previously truncated at its first thousands group) made five Nolan films sweep
 * all five slides, and the rail underneath repeated the same five titles.
 */
const iso = (daysAgo: number) => {
	const d = new Date();
	d.setDate(d.getDate() - daysAgo);
	return d.toISOString().slice(0, 10);
};

const THIS_YEAR = new Date().getFullYear();

let nextId = 1;
function makeTitle(over: Partial<TitleIndex> = {}): TitleIndex {
	return {
		id: nextId++,
		slug: 'x',
		title: `Title ${nextId}`,
		title_en: null,
		title_type: 'film',
		year: THIS_YEAR,
		rating: 75,
		votes_count: 500,
		runtime_min: 100,
		poster: 'https://example.test/p.jpg',
		genres: ['Drama'],
		platforms: ['Netflix'],
		countries: ['USA'],
		tags: [],
		vod_date: iso(5),
		link: '',
		root_id: 1,
		root_title_id: null,
		is_toplevel: true,
		season_no: null,
		episode_no: null,
		...over
	} as TitleIndex;
}

const dimensions = { platforms: ['Netflix'], genres: ['Drama'], countries: [], tags: [], types: [] };

/**
 * load() takes the catalog from `fetch`, not from `parent()` — the layout stopped
 * shipping the index to every route, so each route that browses it asks for it
 * itself. Stubbing `fetch` keeps these tests running against the real load(); the
 * stub is deliberately narrow so a load() that starts fetching something else fails
 * loudly rather than silently receiving titles.
 */
// loadTitles caches module-wide, so without this every case after the first would
// silently be ranking the FIRST case's catalog.
beforeEach(() => __resetTitlesCache());

const run = (titles: TitleIndex[]) =>
	(load as any)({
		parent: async () => ({ dimensions }),
		fetch: async (url: string) => {
			if (!String(url).includes('titles_index.json')) {
				throw new Error(`unexpected fetch in load(): ${url}`);
			}
			return { json: async () => titles };
		}
	}) as Promise<any>;

/** Enough filler for the carousel to have real choices to make. */
const filler = (n: number, over: Partial<TitleIndex> = {}) =>
	Array.from({ length: n }, (_, i) =>
		makeTitle({ rating: 70 + (i % 5), genres: [`Filler${i % 6}`], ...over })
	);

describe('the carousel ranks by confidence, not popularity', () => {
	test('a 95% rating from 11 votes does not outrank 85% from 2000', async () => {
		const fluke = makeTitle({ rating: 95, votes_count: 11, genres: ['Fluke'] });
		const solid = makeTitle({ rating: 85, votes_count: 2000, genres: ['Solid'] });
		const data = await run([fluke, solid, ...filler(20)]);
		const ids = data.featuredList.map((t: TitleIndex) => t.id);
		expect(ids).toContain(solid.id);
		if (ids.includes(fluke.id)) {
			expect(ids.indexOf(solid.id)).toBeLessThan(ids.indexOf(fluke.id));
		}
	});

	/**
	 * The reason a vote FLOOR was rejected: votes accumulate with age, so a floor
	 * filters age rather than quality. In the 0–7 day slice the median is 0 votes.
	 */
	test('a title released days ago is eligible on a handful of votes', async () => {
		const fresh = makeTitle({
			rating: 88,
			votes_count: 24,
			vod_date: iso(2),
			title_type: 'seriál',
			genres: ['Fresh']
		});
		const data = await run([fresh, ...filler(20, { votes_count: 3000 })]);
		expect(data.featuredList.map((t: TitleIndex) => t.id)).toContain(fresh.id);
	});
});

describe('the carousel is a cross-section, not one genre', () => {
	const mixed = () => [
		// six near-identical blockbusters — without quotas they take every slot
		...Array.from({ length: 6 }, () =>
			makeTitle({ rating: 91, votes_count: 100_000, year: 2008, genres: ['Akční'] })
		),
		...Array.from({ length: 6 }, (_, i) =>
			makeTitle({
				title_type: 'seriál',
				rating: 78 + i,
				votes_count: 300,
				genres: [`Ser${i}`]
			})
		),
		...filler(12)
	];

	test('at least two serials get a slot', async () => {
		const data = await run(mixed());
		const serials = data.featuredList.filter((t: TitleIndex) => t.title_type === 'seriál');
		expect(serials.length).toBeGreaterThanOrEqual(2);
	});

	test('at most one title older than the last ~2 years', async () => {
		const data = await run(mixed());
		const legacy = data.featuredList.filter((t: TitleIndex) => (t.year ?? 0) < THIS_YEAR - 2);
		expect(legacy.length).toBeLessThanOrEqual(1);
	});

	test('no lead genre takes more than two slots', async () => {
		const data = await run(mixed());
		const counts = new Map<string, number>();
		for (const t of data.featuredList as TitleIndex[]) {
			const g = t.genres[0] ?? '—';
			counts.set(g, (counts.get(g) ?? 0) + 1);
		}
		expect(Math.max(...counts.values())).toBeLessThanOrEqual(2);
	});

	test('the carousel still fills every slot when the quotas cannot be met', async () => {
		// nothing but old action films — quotas are unsatisfiable, but a half-empty
		// carousel is worse than a repeated genre
		const only = Array.from({ length: 8 }, () =>
			makeTitle({ rating: 88, votes_count: 50_000, year: 1999, genres: ['Akční'] })
		);
		const data = await run(only);
		expect(data.featuredList).toHaveLength(5);
	});
});

describe('the page does not show the same titles twice', () => {
	test('the rail below the carousel excludes what the carousel shows', async () => {
		const data = await run(mixedPool());
		const featured = new Set((data.featuredList as TitleIndex[]).map((t) => t.id));
		const repeated = (data.bestThisMonth as TitleIndex[]).filter((t) => featured.has(t.id));
		expect(repeated).toEqual([]);
	});

	function mixedPool() {
		return [
			...Array.from({ length: 10 }, (_, i) =>
				makeTitle({ rating: 90 - i, votes_count: 5000, genres: [`G${i}`] })
			),
			...Array.from({ length: 6 }, (_, i) =>
				makeTitle({ title_type: 'seriál', rating: 80 + i, votes_count: 400, genres: [`S${i}`] })
			)
		];
	}
});

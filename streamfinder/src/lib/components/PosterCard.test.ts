import { describe, expect, test } from 'vitest';
import { render } from 'vitest-browser-svelte';
import PosterCard from './PosterCard.svelte';
import type { TitleIndex } from '$lib/types';

/**
 * Fixtures are chosen by DATA SHAPE, not by which title is famous.
 *
 * Every bug this file exists to catch was a shape nobody rendered while
 * developing: an episode whose ČSFD name is a bare clock time, a season row
 * whose name just repeats the serial, a work with no genres at all. Picking
 * "Ted Lasso" as a fixture tests one shape; picking the extremes tests the ones
 * that actually break. The counts in the comments come from a real sweep of
 * 15 694 child rows (scripts/shape_sweep.py).
 */
function makeTitle(over: Partial<TitleIndex> = {}): TitleIndex {
	return {
		id: 1,
		slug: 'test-2024',
		title: 'Test',
		title_en: null,
		title_type: 'film',
		year: 2024,
		rating: 75,
		votes_count: 500,
		runtime_min: 100,
		poster: 'https://example.test/p.jpg',
		genres: ['Drama', 'Thriller'],
		platforms: ['Netflix'],
		countries: ['USA'],
		tags: [],
		crew_ids: [],
		vod_date: '2024-01-01',
		link: 'https://www.csfd.cz/film/1-test/prehled/',
		root_id: 1,
		root_title_id: 1,
		is_toplevel: true,
		season_no: null,
		episode_no: null,
		...over
	} as TitleIndex;
}

const sub = (c: HTMLElement) => c.querySelector('.card-sub')?.textContent?.trim() ?? null;
const headline = (c: HTMLElement) => c.querySelector('.card-title')?.textContent?.trim() ?? null;
const seTag = (c: HTMLElement) => c.querySelector('.se-tag')?.textContent?.trim() ?? null;

describe('the sub-line always means "genre"', () => {
	/**
	 * The regression this file was written for. The slot under the title used to
	 * hold the genre for works but the episode name for children, so the eye could
	 * never learn what it meant — and roughly 1 in 6 ČSFD episode names is
	 * unusable as a label.
	 */
	test.for([
		// [case, overrides] — each row is a real shape from the catalog
		['episode with a real name', { title: 'Paměť (S03E05)', season_no: 3, episode_no: 5 }],
		['episode named by number only', { title: 'Epizoda 11 (S27E11)', season_no: 27, episode_no: 11 }],
		['episode named as a clock time', { title: '21:00 (S02E15)', season_no: 2, episode_no: 15 }],
		['episode with a one-letter name', { title: 'VI (E06)', episode_no: 6 }],
		['season row repeating the serial', { title: 'Young Rock- Season 1', season_no: 1 }]
	] as const)('%s shows genres, not the episode name', async ([, over]) => {
		const { container } = await render(PosterCard, {
			title: makeTitle({ is_toplevel: false, title_type: 'epizoda', ...over }),
			serialTitle: 'Serial'
		});
		expect(sub(container)).toBe('Drama · Thriller');
	});

	test('a top-level work shows genres too', async () => {
		const { container } = await render(PosterCard, { title: makeTitle() });
		expect(sub(container)).toBe('Drama · Thriller');
	});

	test('at most two genres, so the line cannot wrap or truncate', async () => {
		const { container } = await render(PosterCard, {
			title: makeTitle({ genres: ['Drama', 'Thriller', 'Krimi', 'Mysteriózní'] })
		});
		expect(sub(container)).toBe('Drama · Thriller');
	});

	test('no genres renders no sub-line at all, rather than an empty row', async () => {
		const { container } = await render(PosterCard, { title: makeTitle({ genres: [] }) });
		expect(container.querySelector('.card-sub')).toBeNull();
	});
});

describe('episode position is carried by the badge', () => {
	test('season and episode', async () => {
		const { container } = await render(PosterCard, {
			title: makeTitle({ is_toplevel: false, season_no: 3, episode_no: 5 })
		});
		expect(seTag(container)).toBe('S3·E5');
	});

	test('episode with no season', async () => {
		const { container } = await render(PosterCard, {
			title: makeTitle({ is_toplevel: false, season_no: null, episode_no: 7 })
		});
		expect(seTag(container)).toBe('E7');
	});

	test('a season row', async () => {
		const { container } = await render(PosterCard, {
			title: makeTitle({ is_toplevel: false, season_no: 2, episode_no: null })
		});
		expect(seTag(container)).toBe('2. série');
	});

	test('a top-level work has no badge', async () => {
		const { container } = await render(PosterCard, { title: makeTitle() });
		expect(container.querySelector('.se-tag')).toBeNull();
	});
});

describe('the headline', () => {
	test('a child in the Kalendár leads with the serial name', async () => {
		const { container } = await render(PosterCard, {
			title: makeTitle({ is_toplevel: false, title: 'Paměť (S03E05)', season_no: 3, episode_no: 5 }),
			serialTitle: 'Silo'
		});
		expect(headline(container)).toBe('Silo');
	});

	test('the (S03E05) marker never reaches the screen', async () => {
		const { container } = await render(PosterCard, {
			title: makeTitle({ title: 'Paměť (S03E05)', season_no: 3, episode_no: 5 })
		});
		expect(headline(container)).toBe('Paměť');
	});

	/**
	 * Defence in depth: the parser strips these at extraction now, but an older
	 * export must not put invisible characters back on screen.
	 */
	test('bidi isolates from ČSFD are stripped', async () => {
		const { container } = await render(PosterCard, {
			title: makeTitle({ title: '⁨Charlotte⁩ (E05)', episode_no: 5 })
		});
		expect(headline(container)).toBe('Charlotte');
	});
});

describe('missing data degrades quietly', () => {
	test('no poster falls back to a placeholder carrying the name', async () => {
		const { container } = await render(PosterCard, {
			title: makeTitle({ poster: null, title: 'Roma 96' })
		});
		expect(container.querySelector('.poster-placeholder')?.textContent?.trim()).toBe('Roma 96');
	});

	test('no rating of its own shows the inherited one, marked as approximate', async () => {
		const { container } = await render(PosterCard, {
			title: makeTitle({ rating: null, inherited_rating: 68, inherited_from: 'seriál' })
		});
		const rating = container.querySelector('.card-rating');
		expect(rating?.textContent).toContain('68');
		expect(rating?.textContent).toContain('≈');
	});

	test('no rating at all shows none', async () => {
		const { container } = await render(PosterCard, { title: makeTitle({ rating: null }) });
		expect(container.querySelector('.card-rating')).toBeNull();
	});

	/** 260 real titles carry an empty platforms array — the key is always present. */
	test('no platforms renders no platform badge', async () => {
		const { container } = await render(PosterCard, { title: makeTitle({ platforms: [] }) });
		expect(container.querySelector('.platform-tag')).toBeNull();
	});

	test('a running serial is badged', async () => {
		const { container } = await render(PosterCard, {
			title: makeTitle({ title_type: 'seriál', is_running: true })
		});
		expect(container.querySelector('.live-tag')).not.toBeNull();
	});
});

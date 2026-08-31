import { describe, expect, test } from 'vitest';
import { buildSearchIndex, fold, matchedName, matchesQuery, rankHit } from './search';
import type { TitleIndex } from './types';

/**
 * Fixtures are real catalog rows, because the bug this file guards against is a
 * data shape, not a code path: ČSFD's first alternative name is the
 * country-of-ORIGIN one, so `title_en` holds "Ojingeo geim" and the "Squid Game"
 * a user types lives further down the list. Search matched title + title_en only,
 * and every foreign title whose English name was not also its origin name was
 * unreachable.
 */
function t(over: Partial<TitleIndex>): TitleIndex {
	return {
		id: 1,
		title: 'Test',
		title_en: null,
		root_id: 1,
		is_toplevel: true,
		...over
	} as TitleIndex;
}

const squidGame = t({
	id: 1,
	title: 'Hra na oliheň',
	title_en: 'Ojingeo geim',
	alt: ['오징어 게임', 'Squid Game'],
	root_id: 772224
});
const squidSeason3 = t({
	id: 2,
	title: 'Hra na oliheň- Série 3',
	title_en: null,
	is_toplevel: false,
	root_id: 772224
});
const spiritedAway = t({
	id: 3,
	title: 'Cesta do fantazie',
	title_en: 'Sen to Čihiro no kamikakuši',
	alt: ['千と千尋の神隠し', 'Sen to Chihiro no kamikakushi', 'Cesta do fantázie', 'Spirited Away'],
	root_id: 42136
});
const otto = t({ id: 4, title: 'Muž jménem Otto', title_en: 'A Man Called Otto', root_id: 5 });

const catalog = [squidGame, squidSeason3, spiritedAway, otto];

function find(query: string) {
	const index = buildSearchIndex(catalog);
	const q = fold(query.trim());
	return catalog.filter((x) => matchesQuery(index, x, q)).map((x) => x.id);
}

describe('a title is findable under every name it was released with', () => {
	test('the English name, even when it is not the origin name', () => {
		expect(find('squid game')).toContain(1);
		expect(find('spirited away')).toContain(3);
	});

	test('the origin name and the Czech name keep working', () => {
		expect(find('hra na oliheň')).toContain(1);
		expect(find('ojingeo')).toContain(1);
		expect(find('a man called otto')).toContain(4);
	});

	test('diacritics are optional in both the query and the data', () => {
		expect(find('hra na olihen')).toContain(1);
		expect(find('cesta do fantazie')).toContain(3);
		// The Slovak name carries different accents than the query typed here.
		expect(find('fantazie')).toContain(3);
	});

	test('the original script matches when pasted', () => {
		// The serial and the season that borrows its names — nothing else.
		expect(find('오징어')).toEqual([1, 2]);
	});

	test('a season inherits its serial names — ČSFD lists none on season pages', () => {
		// The Kalendár lists releases, so "squid game" must reach Série 3 as well.
		expect(find('squid game')).toEqual([1, 2]);
	});

	test('a query that matches nothing still matches nothing', () => {
		expect(find('mandalorian')).toEqual([]);
	});
});

describe('the matched name is reported so a hit does not look wrong', () => {
	test('an alternative name is returned when the visible title does not match', () => {
		expect(matchedName(squidGame, fold('squid'))).toBe('Squid Game');
		expect(matchedName(spiritedAway, fold('spirited'))).toBe('Spirited Away');
	});

	test('null when the title itself already contains the query', () => {
		expect(matchedName(squidGame, fold('oliheň'))).toBeNull();
	});
});

describe('the index is a lookup, not a requirement', () => {
	test('a title missing from the index still matches on its own fields', () => {
		expect(matchesQuery(new Map(), otto, fold('called otto'))).toBe(true);
		expect(matchesQuery(new Map(), otto, fold('otto'))).toBe(true);
		expect(matchesQuery(new Map(), otto, fold('nope'))).toBe(false);
	});
});

describe('the best answer to the query sorts first', () => {
	// The overlay shows 8 results. Ranking by index order answered "squid game" with
	// two making-of documentaries and put the series itself fourth.
	const making = t({
		id: 5,
		title: 'Jak vznikala Hra na oliheň: Výzva',
		title_en: 'Making Squid Game: The Challenge',
		root_id: 6
	});
	const challenge = t({
		id: 6,
		title: 'Hra na oliheň: Výzva',
		title_en: 'Squid Game: The Challenge',
		root_id: 7
	});

	test('an exact name beats a prefix, which beats a mention in the middle', () => {
		const q = fold('squid game');
		expect(rankHit(squidGame, q)).toBeLessThan(rankHit(challenge, q));
		expect(rankHit(challenge, q)).toBeLessThan(rankHit(making, q));
	});

	test('a work outranks a season that matched on inherited names', () => {
		const q = fold('hra na oliheň');
		expect(rankHit(squidGame, q)).toBeLessThan(rankHit(squidSeason3, q));
	});
});

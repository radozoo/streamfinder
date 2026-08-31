import type { TitleIndex } from '$lib/types';

/**
 * Case- and diacritic-insensitive text folding for search.
 *
 * NFD decomposition splits accented letters into a base letter + a combining
 * mark (stripped here). So a title with Czech diacritics still matches a query
 * typed without them: a Slovak user can type plain ASCII and find it.
 */
export function fold(s: string): string {
	return s
		.normalize('NFD')
		.replace(/[̀-ͯ]/g, '') // strip combining diacritical marks
		.toLowerCase();
}

/**
 * Folded haystack per title id: every name the title can be found under.
 *
 * Matching only `title` + `title_en` missed most foreign titles, because `title_en`
 * is the country-of-ORIGIN name — "Hra na oliheň" is stored as "Ojingeo geim",
 * "Cesta do fantazie" as "Sen to Čihiro no kamikakuši" — while the English name a
 * user actually types sits in `alt`. Two things happen here:
 *
 *  - every name is folded ONCE per data load instead of on every keystroke (the
 *    catalog filter walks all ~51 k rows per character typed), and
 *  - a season/episode inherits its serial's names, since ČSFD lists none of its own
 *    on those pages: without this, "squid game" finds the serial but not the Série 3
 *    release sitting in the Kalendár.
 */
export function buildSearchIndex(titles: TitleIndex[]): Map<number, string> {
	const names = (t: TitleIndex) => [t.title, t.title_en ?? '', ...(t.alt ?? [])].join(' ');

	// Pass 1: the works, keyed by root id, so their releases can borrow the names.
	const byRoot = new Map<number, string>();
	for (const t of titles) {
		if (t.is_toplevel && t.root_id !== null) byRoot.set(t.root_id, names(t));
	}

	const index = new Map<number, string>();
	for (const t of titles) {
		const inherited = !t.is_toplevel && t.root_id !== null ? byRoot.get(t.root_id) : undefined;
		index.set(t.id, fold(inherited ? `${names(t)} ${inherited}` : names(t)));
	}
	return index;
}

// Built once per titles array, on the first search rather than at page load —
// folding 51 k rows costs enough to be felt on a first paint, and most visits never
// type anything. Keyed on the array itself so a fresh load builds a fresh index and
// the old one is collectable.
const indexCache = new WeakMap<TitleIndex[], Map<number, string>>();

export function getSearchIndex(titles: TitleIndex[]): Map<number, string> {
	let index = indexCache.get(titles);
	if (!index) {
		index = buildSearchIndex(titles);
		indexCache.set(titles, index);
	}
	return index;
}

/**
 * Does the title match an already-folded query? `index` comes from
 * getSearchIndex; the fallback (no index, or a title missing from it) matches on the
 * title's own fields so a row is never silently unfindable.
 */
export function matchesQuery(
	index: Map<number, string> | null,
	t: TitleIndex,
	foldedQuery: string
): boolean {
	const haystack = index?.get(t.id);
	if (haystack !== undefined) return haystack.includes(foldedQuery);
	return fold(t.title).includes(foldedQuery) || fold(t.title_en ?? '').includes(foldedQuery);
}

/**
 * The alternative name a hit matched on, or null when the visible title already
 * contains the query. Searching "Squid Game" returns a row titled "Hra na oliheň",
 * which looks like a wrong result unless the matched name is shown alongside it.
 */
export function matchedName(t: TitleIndex, foldedQuery: string): string | null {
	if (fold(t.title).includes(foldedQuery)) return null;
	for (const name of [t.title_en ?? '', ...(t.alt ?? [])]) {
		if (name && fold(name).includes(foldedQuery)) return name;
	}
	return null;
}

/**
 * How well a hit answers the query — lower sorts first.
 *
 * Substring matching alone left the order to the index, so "squid game" led with two
 * making-of documentaries and put the series fourth. The rules, in order: a name that
 * IS the query beats a name that starts with it, which beats a name that merely
 * contains it; and a work beats its own seasons and episodes, which match only
 * through the names they inherit.
 */
export function rankHit(t: TitleIndex, foldedQuery: string): number {
	let best = 3;
	for (const name of [t.title, t.title_en ?? '', ...(t.alt ?? [])]) {
		if (!name) continue;
		const folded = fold(name);
		if (folded === foldedQuery) best = Math.min(best, 0);
		else if (folded.startsWith(foldedQuery)) best = Math.min(best, 1);
		else if (folded.includes(foldedQuery)) best = Math.min(best, 2);
	}
	return best * 2 + (t.is_toplevel ? 0 : 1);
}

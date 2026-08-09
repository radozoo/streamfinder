import type { TitleIndex } from '$lib/types';

/**
 * Splitting one calendar day into runs of a single title type.
 *
 * The Kalendár already sorted a day by type before any of this existed — seriál,
 * série, film, tv film, epizoda, then everything else — so the groups were there,
 * just invisible. This turns each run into something the page can put a heading and
 * a divider around.
 */

/**
 * Heading for a run. `title_type` is a singular display label from the catalog
 * ("seriál"), and a heading over four cards reads wrong in the singular. Only the
 * types that actually fill a day are declined; anything rarer keeps its own label,
 * which beats guessing a Czech plural for "festivalový název".
 */
const TYPE_HEADING: Record<string, string> = {
	'seriál': 'Seriály',
	'série': 'Série',
	'film': 'Filmy',
	'tv film': 'TV filmy',
	'epizoda': 'Epizody',
	'pořad': 'Pořady'
};

export type TypeRun = { type: string; heading: string; titles: TitleIndex[] };

/**
 * Group by type, keeping the order the caller's sort already established.
 *
 * Keyed by type rather than walking neighbours: everything outside the calendar's
 * TYPE_RANK shares one rank, so a day holding a pořad and a koncert interleaves them
 * by vote count, and a neighbour-walk would emit four one-card runs out of two types.
 */
export function typeRuns(titles: TitleIndex[]): TypeRun[] {
	const runs = new Map<string, TypeRun>();
	for (const t of titles) {
		const type = t.title_type ?? 'ostatní';
		let run = runs.get(type);
		if (!run) {
			run = { type, heading: TYPE_HEADING[type] ?? type, titles: [] };
			runs.set(type, run);
		}
		run.titles.push(t);
	}
	return [...runs.values()];
}

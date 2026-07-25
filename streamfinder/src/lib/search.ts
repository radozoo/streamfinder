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
		.replace(/[\u0300-\u036f]/g, '') // strip combining diacritical marks
		.toLowerCase();
}

// Brand accent per streaming service — a platform is recognised by its colour
// before its name is read, which is exactly what a release calendar needs.
const BRAND: Record<string, string> = {
	Netflix: '#E50914',
	'Prime Video': '#1399e6',
	Prime: '#1399e6',
	'Disney+': '#1a3fce',
	'HBO Max': '#8b5cf6',
	'Apple TV': '#1c1c1e',
	'Apple TV+': '#1c1c1e',
	'Paramount+': '#0064ff',
	'Canal+': '#2b2f3a',
	Hulu: '#0b8f4f',
	Peacock: '#05030d',
	Showtime: '#b30000',
	'AMC+': '#d80f2f',
	'MGM+': '#a6192e',
	'Discovery+': '#0077c8',
	'BBC iPlayer': '#ff4e98',
	ITVX: '#d81f8c',
	'Acorn TV': '#2e7d32',
	'Movistar+': '#019df4',
	Viaplay: '#e0001a',
	Crunchyroll: '#f47521',
	'prima+': '#e4002b',
	YouTube: '#ff0000',
	'YouTube Movies': '#ff0000',
	'YouTube Premium': '#ff0000',
	'Rakuten.tv': '#bf0000',
	'JOJ Play': '#e2001a',
	SkyShowtime: '#6e4ef6',
	'iVysílání': '#0066b3',
	Oneplay: '#00b3a4'
};

// Subscription services surfaced as tiles in the landing page's "Podle platformy"
// section, in priority order. Deliberately NOT the six largest by title count:
// Apple TV is the biggest (16.5k) but it is a rent/buy store, and a tile promising
// titles to browse should lead somewhere you can watch on a subscription you
// already hold. Oneplay is the largest Czech service — leaving it off a Czech VOD
// site was the real gap.
//
// Every name here must exist in dimensions.platforms, or the tile silently
// disappears: that is how "Max" vanished after it was merged into "HBO Max".
// Asserted by home-platforms.test.ts.
export const HOME_PLATFORMS = [
	'Netflix',
	'Disney+',
	'HBO Max',
	'Prime Video',
	'Oneplay',
	'Apple TV+'
];

const NEUTRAL = '#334155'; // slate for services without a defined brand colour

export function platformColor(name: string | undefined | null): string {
	return (name && BRAND[name]) || NEUTRAL;
}

// Search-URL template per service, used as a fallback when CSFD gives us the
// platform name but no direct deep-link (common for titles listed via the /vod
// calendar). `{q}` is replaced with the URL-encoded title. Only services with a
// known, stable search endpoint are listed; anything else stays a plain badge.
const SEARCH: Record<string, string> = {
	Netflix: 'https://www.netflix.com/search?q={q}',
	'Prime Video': 'https://www.primevideo.com/search?phrase={q}',
	Prime: 'https://www.primevideo.com/search?phrase={q}',
	'Disney+': 'https://www.disneyplus.com/search?q={q}',
	'HBO Max': 'https://www.max.com/search?q={q}',
	'Apple TV': 'https://tv.apple.com/search?term={q}',
	'Apple TV+': 'https://tv.apple.com/search?term={q}',
	'Paramount+': 'https://www.paramountplus.com/search/?query={q}',
	Hulu: 'https://www.hulu.com/search?q={q}',
	Peacock: 'https://www.peacocktv.com/watch/search?q={q}',
	'BBC iPlayer': 'https://www.bbc.co.uk/iplayer/search?q={q}',
	SkyShowtime: 'https://www.skyshowtime.com/search?q={q}',
	Crunchyroll: 'https://www.crunchyroll.com/search?q={q}',
	YouTube: 'https://www.youtube.com/results?search_query={q}',
	'YouTube Movies': 'https://www.youtube.com/results?search_query={q}',
	'YouTube Premium': 'https://www.youtube.com/results?search_query={q}',
	'Rakuten.tv': 'https://www.rakuten.tv/cz/search?q={q}',
	'prima+': 'https://www.iprima.cz/vyhledavani?query={q}'
};

/** Search URL for `title` on `name`, or null if that service has no known search. */
export function platformSearchUrl(
	name: string | undefined | null,
	title: string | undefined | null
): string | null {
	if (!name || !title) return null;
	const tpl = SEARCH[name];
	return tpl ? tpl.replace('{q}', encodeURIComponent(title)) : null;
}

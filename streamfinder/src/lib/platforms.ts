// Brand accent per streaming service — a platform is recognised by its colour
// before its name is read, which is exactly what a release calendar needs.
const BRAND: Record<string, string> = {
	Netflix: '#E50914',
	'Prime Video': '#1399e6',
	Prime: '#1399e6',
	'Disney+': '#1a3fce',
	'HBO Max': '#8b5cf6',
	Max: '#0046ff',
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
	Voyo: '#e50914',
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

const NEUTRAL = '#334155'; // slate for services without a defined brand colour

export function platformColor(name: string | undefined | null): string {
	return (name && BRAND[name]) || NEUTRAL;
}

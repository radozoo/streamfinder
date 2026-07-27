import type { EpisodeRelease } from './types';

/** Rating color — always the brand amber, everywhere a numeric ČSFD rating is
 * shown (card, modal, detail page), so a score never changes hue by context. */
export function ratingColor(r: number | null | undefined): string {
	return r ? 'var(--amber)' : 'var(--text-muted)';
}

// Czech plural: 1 → one, 2–4 → few, 5+ → many
export function czPlural(n: number, one: string, few: string, many: string): string {
	if (n === 1) return one;
	if (n >= 2 && n <= 4) return few;
	return many;
}

interface ShapeSource {
	season_count?: number;
	episode_count?: number;
	title_type?: string | null;
}

/** Serial shape line: "2 série · 18 epizod" — shared by the modal and the
 * standalone title page, so a series always describes itself the same way. */
export function shapeText(t: ShapeSource | null | undefined): string | null {
	if (!t) return null;
	const parts: string[] = [];
	if (t.season_count && t.season_count > 1) {
		parts.push(`${t.season_count} ${czPlural(t.season_count, 'série', 'série', 'sérií')}`);
	}
	if (t.episode_count) {
		const w: [string, string, string] =
			t.title_type === 'pořad' ? ['díl', 'díly', 'dílů'] : ['epizoda', 'epizody', 'epizod'];
		parts.push(`${t.episode_count} ${czPlural(t.episode_count, w[0], w[1], w[2])}`);
	}
	return parts.join(' · ') || null;
}

export interface SeasonGroup {
	season: number | null;
	eps: EpisodeRelease[];
	first: string | null;
	last: string | null;
}

/** Group a serial's episode releases by season for the availability timeline. */
export function buildSeasons(eps: EpisodeRelease[] | null | undefined): SeasonGroup[] {
	if (!eps || !eps.length) return [];
	const map = new Map<number, EpisodeRelease[]>();
	for (const e of eps) {
		const s = e.season_no ?? 0;
		if (!map.has(s)) map.set(s, []);
		map.get(s)!.push(e);
	}
	return [...map.entries()]
		.sort((a, b) => a[0] - b[0])
		.map(([season, list]) => {
			const dates = list.map((e) => e.vod_date).filter((d): d is string => !!d).sort();
			return { season: season || null, eps: list, first: dates[0] ?? null, last: dates.at(-1) ?? null };
		});
}

export function dotPos(e: EpisodeRelease, first: string | null, last: string | null): number {
	if (!e.vod_date || !first || !last || first === last) return 50;
	const t0 = +new Date(first), t1 = +new Date(last), t = +new Date(e.vod_date);
	return Math.max(0, Math.min(100, ((t - t0) / (t1 - t0)) * 100));
}

export function shortDate(d: string | null): string {
	if (!d) return '';
	const [, mo, day] = d.split('-');
	return `${Number(day)}. ${Number(mo)}.`;
}

export function cadenceLabel(days: number | null | undefined): string | null {
	if (days == null) return null;
	if (days <= 0) return 'celá séria naraz';
	if (days === 1) return 'denně';
	if (days <= 4) return `ob ${days} dny`;
	if (days <= 10) return 'týdně';
	return `ob ~${days} dní`;
}

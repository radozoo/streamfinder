import type { TitleIndex } from './types';

/**
 * When a title actually landed on VOD — every time, not just once.
 *
 * ČSFD lists a running serial's root again every week a new episode drops, and lists
 * a film again when it reaches a second platform years later. `vod_date` is a single
 * field and can hold only one of those, so a title could appear on exactly one day of
 * the Kalendár: 3,977 (day, title) releases were invisible, on 258 of the last 365
 * days. The exporter now ships the full list as `vod_events`, but only for the 3,396
 * titles where it says something `vod_date` does not — everything else still carries
 * `vod_date` alone.
 *
 * That fallback is the reason these two helpers exist. Every consumer would otherwise
 * repeat the same `vod_events ?? [vod_date]` dance, and the one that forgot would
 * quietly drop 46,000 single-release titles off the calendar.
 */

/** Every release as [date, platform], oldest first. Platform is null when unknown. */
export function releasesOf(t: TitleIndex): [string, string | null][] {
	if (t.vod_events?.length) return t.vod_events;
	return t.vod_date ? [[t.vod_date, null]] : [];
}

/**
 * The distinct days this title was released on.
 *
 * Distinct, because a title that reached two platforms on the same day has two
 * events and must still render once on that day, not twice.
 */
export function releaseDates(t: TitleIndex): string[] {
	if (!t.vod_events?.length) return t.vod_date ? [t.vod_date] : [];
	const seen = new Set<string>();
	for (const [date] of t.vod_events) seen.add(date);
	return [...seen];
}

/**
 * Does this title belong on the calendar at all?
 *
 * Allocation-free on purpose: the facet predicates run it over all ~51k titles on
 * every keystroke, so it must not build the array `releaseDates` does.
 */
export function hasRelease(t: TitleIndex): boolean {
	return Boolean(t.vod_date) || Boolean(t.vod_events?.length);
}

/** Today as YYYY-MM-DD — the same UTC day the Kalendár splits past from upcoming on. */
export const todayISO = (): string => new Date().toISOString().slice(0, 10);

/**
 * The first day this title is (or will be) watchable, or null when it has no date.
 *
 * Not `vod_date`: for a running serial that is often the NEXT episode, so it sits in
 * the future while the show has been streaming for months. The oldest of everything
 * we know is the honest answer. `first_vod_date` matters on its own because a serial
 * announced but not yet out can carry it with no `vod_date` at all.
 */
export function firstRelease(t: TitleIndex): string | null {
	let first = t.vod_events?.[0]?.[0] ?? '';
	for (const d of [t.vod_date, t.first_vod_date]) if (d && (!first || d < first)) first = d;
	return first || null;
}

/**
 * Announced but not out yet: every known release lies after today.
 *
 * A title with no date at all is NOT planned — it is just undated (a third of the
 * catalog), and marking those would bury the real signal.
 */
export function isPlanned(t: TitleIndex, today: string = todayISO()): boolean {
	const first = firstRelease(t);
	return first !== null && first > today;
}

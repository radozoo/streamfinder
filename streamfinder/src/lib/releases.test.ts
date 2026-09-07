import { describe, expect, test } from 'vitest';
import { hasRelease, releaseDates, releasesOf } from './releases';
import type { TitleIndex } from './types';

/**
 * The Kalendár groups by these dates, so a mistake here is silent: the day simply
 * shows fewer titles than ČSFD's own listing does, which is exactly the bug that
 * hid 3,977 releases across 258 of the last 365 days.
 */
const t = (vod_date: string | null, vod_events?: [string, string | null][]) =>
	({ id: 1, title: 't', vod_date, vod_events }) as unknown as TitleIndex;

describe('a title with a single release', () => {
	test('falls back to vod_date — the ~46k titles that carry no vod_events', () => {
		expect(releaseDates(t('2026-09-07'))).toEqual(['2026-09-07']);
		expect(releasesOf(t('2026-09-07'))).toEqual([['2026-09-07', null]]);
		expect(hasRelease(t('2026-09-07'))).toBe(true);
	});

	test('with no date at all is off the calendar, not on it as undefined', () => {
		expect(releaseDates(t(null))).toEqual([]);
		expect(releasesOf(t(null))).toEqual([]);
		expect(hasRelease(t(null))).toBe(false);
	});
});

describe('a title released more than once', () => {
	const colision = t('2026-09-28', [
		['2026-09-07', 'HBO Max'],
		['2026-09-14', 'HBO Max'],
		['2026-09-21', 'HBO Max'],
		['2026-09-28', 'HBO Max']
	]);

	test('appears on every date, not only the one vod_date kept', () => {
		expect(releaseDates(colision)).toEqual([
			'2026-09-07',
			'2026-09-14',
			'2026-09-21',
			'2026-09-28'
		]);
	});

	test('keeps the platform of each release — Vigil in 2023 was not BBC iPlayer', () => {
		const vigil = t('2023-12-17', [
			['2023-12-17', 'Voyo'],
			['2026-09-06', 'BBC iPlayer']
		]);
		expect(releasesOf(vigil)).toEqual([
			['2023-12-17', 'Voyo'],
			['2026-09-06', 'BBC iPlayer']
		]);
	});

	test('renders once on a day it reached two platforms, not twice', () => {
		const twoPlatforms = t('2026-09-07', [
			['2026-09-07', 'Netflix'],
			['2026-09-07', 'Prime Video']
		]);
		expect(releaseDates(twoPlatforms)).toEqual(['2026-09-07']);
		expect(releasesOf(twoPlatforms)).toHaveLength(2);
	});

	test('is on the calendar even when its own row has no vod_date', () => {
		// Four titles are shipped exactly like this — Prominentky and friends carry a
		// listing date while fact_titles.vod_date is NULL. They were off the calendar
		// entirely until the exporter stopped requiring more than one event.
		const orphan = t(null, [['2025-11-15', 'Netflix']]);
		expect(releaseDates(orphan)).toEqual(['2025-11-15']);
		expect(hasRelease(orphan)).toBe(true);
	});
});

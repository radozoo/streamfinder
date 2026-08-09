import { describe, expect, test } from 'vitest';
import { typeRuns } from './type-runs';
import type { TitleIndex } from './types';

/**
 * The Kalendár draws a heading and a divider around each run, so a run that splits
 * when it should not is not a cosmetic problem: the day grows a second "EPIZODY"
 * heading and reads as if something changed between them.
 */
const t = (title_type: string, id = Math.round(Math.random() * 1e6)) =>
	({ id, title: `t${id}`, title_type }) as unknown as TitleIndex;

describe('runs follow the order they arrive in', () => {
	test('one run per type, in first-seen order', () => {
		const runs = typeRuns([t('seriál'), t('seriál'), t('film'), t('epizoda')]);
		expect(runs.map((r) => [r.type, r.titles.length])).toEqual([
			['seriál', 2],
			['film', 1],
			['epizoda', 1]
		]);
	});

	test('a type interrupted by another still forms ONE run', () => {
		// Everything outside the calendar's TYPE_RANK shares a rank, so a pořad and a
		// koncert on the same day interleave by vote count. Walking neighbours would
		// turn two types into four one-card runs, each with its own heading.
		const runs = typeRuns([t('pořad'), t('koncert'), t('pořad'), t('koncert')]);
		expect(runs.length).toBe(2);
		expect(runs.map((r) => r.titles.length)).toEqual([2, 2]);
	});

	test('a day of one type is a single run, not a passthrough', () => {
		const runs = typeRuns([t('epizoda'), t('epizoda'), t('epizoda')]);
		expect(runs.length).toBe(1);
		expect(runs[0].heading).toBe('Epizody');
	});

	test('an empty day has no runs', () => {
		expect(typeRuns([])).toEqual([]);
	});

	test('every title ends up in exactly one run', () => {
		const titles = [t('film', 1), t('epizoda', 2), t('film', 3), t('série', 4)];
		const runs = typeRuns(titles);
		const ids = runs.flatMap((r) => r.titles.map((x) => x.id)).sort();
		expect(ids).toEqual([1, 2, 3, 4]);
	});
});

describe('headings', () => {
	test('the common types are pluralised — a heading is never "seriál"', () => {
		expect(typeRuns([t('seriál')])[0].heading).toBe('Seriály');
		expect(typeRuns([t('film')])[0].heading).toBe('Filmy');
		expect(typeRuns([t('tv film')])[0].heading).toBe('TV filmy');
	});

	test('a rare type keeps its own label rather than an invented plural', () => {
		// "festivalový název" has no sensible one-word plural; showing it as-is is
		// honest, and these appear a handful of times a year.
		expect(typeRuns([t('festivalový název')])[0].heading).toBe('festivalový název');
	});

	test('a title with no type at all lands in one bucket instead of crashing', () => {
		const runs = typeRuns([{ id: 1, title: 'x' } as unknown as TitleIndex]);
		expect(runs.length).toBe(1);
		expect(runs[0].type).toBe('ostatní');
	});
});

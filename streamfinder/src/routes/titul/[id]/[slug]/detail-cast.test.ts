import { describe, expect, test } from 'vitest';
import { render } from 'vitest-browser-svelte';
import DetailPage from './+page.svelte';
import type { TitleDetail } from '$lib/types';

/**
 * The cast list collapses past a limit.
 *
 * This was lost, not broken: it lived only in TitleModal, and when every card was
 * unified onto the detail page the modal was deleted. Parity had been checked by
 * comparing section headings and the fields each surface used — both matched, so
 * the miss was inside a section, in how one field is RENDERED. A ČSFD cast can run
 * past a hundred names and bury the rest of the page under it.
 */
const ACTOR_LIMIT = 20;

function makeDetail(actorCount: number): TitleDetail {
	return {
		id: 1,
		slug: 'x-2024',
		title: 'Test',
		title_en: null,
		title_type: 'film',
		year: 2024,
		rating: 75,
		votes_count: 500,
		runtime_min: 100,
		age_rating: null,
		poster: null,
		backdrop: null,
		trailer_youtube_id: null,
		plot: null,
		genres: ['Drama'],
		tags: [],
		countries: ['USA'],
		platforms: ['Netflix'],
		crew_ids: [],
		vod_date: '2024-01-01',
		link: '',
		root_id: 1,
		root_title_id: null,
		is_toplevel: true,
		season_no: null,
		episode_no: null,
		directors: ['Reżyser'],
		actors: Array.from({ length: actorCount }, (_, i) => `Herec ${i + 1}`),
		screenwriters: [],
		cinematographers: [],
		composers: [],
		reviews: [],
		vods: []
	} as unknown as TitleDetail;
}

const castText = (c: HTMLElement) => {
	const rows = [...c.querySelectorAll('.crew-row')];
	const row = rows.find((r) => r.querySelector('dt')?.textContent?.includes('Hrají'));
	return row?.querySelector('dd')?.textContent ?? '';
};

describe('a long cast list collapses behind a toggle', () => {
	test(`more than ${ACTOR_LIMIT} actors shows the remainder behind "více"`, async () => {
		const { container } = await render(DetailPage, { data: { title: makeDetail(25) } as any });
		const toggle = container.querySelector('.more-toggle');
		expect(toggle).not.toBeNull();
		expect(toggle?.textContent?.trim()).toBe('+ 5 více');
		expect(castText(container)).toContain('Herec 20');
		expect(castText(container)).not.toContain('Herec 21');
	});

	test('the toggle reveals the rest and turns into "méně"', async () => {
		const { container } = await render(DetailPage, { data: { title: makeDetail(25) } as any });
		(container.querySelector('.more-toggle') as HTMLButtonElement).click();
		await new Promise((r) => setTimeout(r, 0));
		expect(castText(container)).toContain('Herec 25');
		expect(container.querySelector('.more-toggle')?.textContent?.trim()).toBe('méně');
	});

	test(`exactly ${ACTOR_LIMIT} actors needs no toggle`, async () => {
		const { container } = await render(DetailPage, { data: { title: makeDetail(20) } as any });
		expect(container.querySelector('.more-toggle')).toBeNull();
		expect(castText(container)).toContain('Herec 20');
	});

	test('a short cast is shown whole', async () => {
		const { container } = await render(DetailPage, { data: { title: makeDetail(3) } as any });
		expect(container.querySelector('.more-toggle')).toBeNull();
		expect(castText(container)).toContain('Herec 3');
	});
});

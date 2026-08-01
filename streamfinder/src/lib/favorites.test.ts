import { beforeEach, describe, expect, test } from 'vitest';
import { render } from 'vitest-browser-svelte';
import FavoriteButton from './components/FavoriteButton.svelte';
import { favorites } from './favorites.svelte';

/**
 * Favourites are the one thing on this site the visitor creates, so the parts that
 * can quietly lose them get the most attention here: the key they are stored under,
 * what happens to a corrupt entry, and whether a title with no ČSFD id can even be
 * hearted (it must not — there would be nothing durable to store).
 */
const KEY = 'streamfinder:favorites:v1';

beforeEach(() => {
	localStorage.clear();
	favorites.clear();
});

describe('the stored list', () => {
	test('toggling on then off leaves nothing behind', () => {
		favorites.toggle(123);
		expect(favorites.has(123)).toBe(true);
		expect(favorites.count).toBe(1);
		favorites.toggle(123);
		expect(favorites.has(123)).toBe(false);
		expect(favorites.count).toBe(0);
	});

	test('newest first — the Oblíbené page reads this order', () => {
		favorites.toggle(1);
		favorites.toggle(2);
		favorites.toggle(3);
		expect(favorites.ids).toEqual([3, 2, 1]);
	});

	test('it survives a reload', () => {
		favorites.toggle(42);
		const raw = JSON.parse(localStorage.getItem(KEY) ?? '{}');
		expect(raw).toEqual({ v: 1, ids: [42] });
	});

	test('a title with no ČSFD id cannot be favourited', () => {
		// The local `id` is not durable, so a row without csfd_id has no key worth
		// storing. Silently ignoring the toggle beats writing something that will
		// point at a different film after the next database rebuild.
		expect(favorites.toggle(null)).toBe(false);
		expect(favorites.toggle(undefined)).toBe(false);
		expect(favorites.count).toBe(0);
	});

	test('a corrupt entry reads as empty instead of throwing', () => {
		localStorage.setItem(KEY, '{ this is not json');
		expect(() => favorites.has(1)).not.toThrow();
	});
});

describe('backup file', () => {
	test('export then import restores the same list', () => {
		favorites.toggle(7);
		favorites.toggle(9);
		const backup = favorites.exportJson();
		favorites.clear();
		expect(favorites.count).toBe(0);
		favorites.importJson(backup);
		expect(favorites.ids.sort()).toEqual([7, 9]);
	});

	test('import merges rather than replaces', () => {
		// Importing on a second device must not wipe what is already there.
		favorites.toggle(1);
		const { added, total } = favorites.importJson(JSON.stringify({ v: 1, ids: [2, 3] }));
		expect(added).toBe(2);
		expect(total).toBe(3);
		expect(favorites.ids.sort()).toEqual([1, 2, 3]);
	});

	test('importing the same file twice adds nothing', () => {
		favorites.importJson(JSON.stringify({ v: 1, ids: [5] }));
		const { added } = favorites.importJson(JSON.stringify({ v: 1, ids: [5] }));
		expect(added).toBe(0);
		expect(favorites.count).toBe(1);
	});

	test('a file from another app is rejected with a message, not a crash', () => {
		expect(() => favorites.importJson(JSON.stringify({ hello: 'world' }))).toThrow();
		expect(favorites.count).toBe(0);
	});
});

describe('the heart button', () => {
	test('reflects and changes the stored state', async () => {
		const { container } = await render(FavoriteButton, { csfdId: 555 });
		const btn = container.querySelector('button') as HTMLButtonElement;
		expect(btn.getAttribute('aria-pressed')).toBe('false');
		btn.click();
		await new Promise((r) => setTimeout(r, 0));
		expect(favorites.has(555)).toBe(true);
		expect(container.querySelector('button')?.getAttribute('aria-pressed')).toBe('true');
	});

	test('renders nothing when there is no id to store', async () => {
		const { container } = await render(FavoriteButton, { csfdId: null });
		expect(container.querySelector('button')).toBeNull();
	});

	test('the label says what the click will do, not what the state is', async () => {
		const { container } = await render(FavoriteButton, { csfdId: 777 });
		expect(container.querySelector('button')?.getAttribute('aria-label')).toBe(
			'Přidat do oblíbených'
		);
	});
});

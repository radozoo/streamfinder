import { describe, expect, test } from 'vitest';
import { HOME_PLATFORMS } from './platforms';
import dimensions from '../../static/data/dimensions.json';

/**
 * The landing page's platform tiles are curated by name, and the template skips
 * any name it cannot find in the data:
 *
 *     {#each HOME_PLATFORMS as p}
 *       {@const dim = data.dimensions.platforms.find((x) => x.name === p)}
 *       {#if dim} … {/if}
 *
 * That guard prevents a crash but hides a rename. When "Max" was merged into
 * "HBO Max" in the exporter's alias map, its tile stopped rendering and the grid
 * quietly dropped to five — no error, no warning, nothing in the console.
 *
 * These tests read the SHIPPED dimensions.json, so a future merge or a ČSFD
 * rename turns the grid red here instead of silently thinning the page.
 */
const byName = new Map(
	(dimensions as { platforms: { name: string; count: number }[] }).platforms.map((p) => [
		p.name,
		p.count
	])
);

describe('landing page platform tiles', () => {
	/**
	 * Guards the guard: if this import ever resolved to a URL string instead of
	 * parsed JSON, `byName` would be empty and every assertion below would pass
	 * vacuously while checking nothing.
	 */
	test('the catalog fixture actually loaded', () => {
		expect(byName.size).toBeGreaterThan(50);
	});

	test.for(HOME_PLATFORMS)('%s exists in the exported catalog', (name) => {
		expect(byName.has(name), `"${name}" has no titles — its tile would silently vanish`).toBe(
			true
		);
	});

	test('every tile leads somewhere worth browsing', () => {
		// A tile advertising a handful of titles is worse than no tile. The smallest
		// curated service should still be a real library.
		for (const name of HOME_PLATFORMS) {
			expect(byName.get(name) ?? 0).toBeGreaterThan(500);
		}
	});

	test('no duplicate tiles', () => {
		expect(new Set(HOME_PLATFORMS).size).toBe(HOME_PLATFORMS.length);
	});

	/**
	 * Not a correctness rule — a prompt. If a service grows past everything we
	 * feature and still is not on the page, that is an editorial decision to make
	 * consciously, the way leaving Oneplay off was not.
	 */
	test('no un-featured subscription service dwarfs the smallest featured one', () => {
		const smallestFeatured = Math.min(...HOME_PLATFORMS.map((p) => byName.get(p) ?? 0));
		// Aggregators and re-streamers are not subscription services we would tile.
		const NOT_A_SUBSCRIPTION = new Set([
			'Apple TV', // rent/buy store
			'YouTube',
			'YouTube Movies',
			'YouTube Premium',
			'Rakuten.tv',
			'Lepší.TV',
			'SledovaniTV',
			'Telly',
			'O2 TV'
		]);
		const overlooked = [...byName.entries()]
			.filter(([n, c]) => !HOME_PLATFORMS.includes(n) && !NOT_A_SUBSCRIPTION.has(n))
			.filter(([, c]) => c > smallestFeatured * 2)
			.map(([n, c]) => `${n} (${c})`);
		expect(overlooked, 'consider featuring these, or add them to the exclusion list').toEqual([]);
	});
});

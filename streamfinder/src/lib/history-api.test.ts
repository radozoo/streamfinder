import { describe, expect, test } from 'vitest';

/**
 * The browser's own history API must not be used for URL state.
 *
 * SvelteKit keeps its router index inside `history.state`. Calling
 * `history.replaceState(null, ...)` — the shape every tutorial shows — wipes it, and
 * the router's popstate handler opens with `if (event.state?.[HISTORY_INDEX])`. With
 * that gone it takes a branch that updates the URL but never navigates: Back looked
 * dead on Katalóg and Kalendár, and a second Back skipped a page.
 *
 * Nothing else catches this. It type-checks, it builds, the URL even changes — the
 * page simply does not move, and only under a real Back button, which no component
 * test presses. So the guard reads the source instead. `import.meta.glob` with
 * `?raw` inlines it at build time, so this works in the browser runner alongside
 * the component tests rather than needing a Node project of its own.
 */
const sources = import.meta.glob('/src/**/*.{svelte,ts}', {
	query: '?raw',
	import: 'default',
	eager: true
}) as Record<string, string>;

const NATIVE_HISTORY_CALL = /\bhistory\s*\.\s*(replace|push)State\s*\(/;

describe('URL state goes through SvelteKit, not the raw history API', () => {
	test('the sweep actually reads the source files', () => {
		// Without this, a glob that silently matches nothing would make every
		// assertion below vacuously true.
		expect(Object.keys(sources).length).toBeGreaterThan(20);
	});

	test('no source file calls history.replaceState or history.pushState', () => {
		const offenders: string[] = [];
		for (const [path, src] of Object.entries(sources)) {
			if (path.endsWith('.test.ts')) continue;
			src.split('\n').forEach((line, i) => {
				const trimmed = line.trim();
				if (trimmed.startsWith('//') || trimmed.startsWith('*')) return;
				if (NATIVE_HISTORY_CALL.test(line)) offenders.push(`${path}:${i + 1}`);
			});
		}
		expect(offenders).toEqual([]);
	});

	test('the pattern it looks for is the one that broke Back', () => {
		expect(NATIVE_HISTORY_CALL.test("history.replaceState(null, '', '?q=x')")).toBe(true);
		expect(NATIVE_HISTORY_CALL.test('history.pushState(null, "", url)')).toBe(true);
		// SvelteKit's import-bound replaceState is the correct call and must pass
		expect(NATIVE_HISTORY_CALL.test("replaceState('?q=x', {})")).toBe(false);
	});
});

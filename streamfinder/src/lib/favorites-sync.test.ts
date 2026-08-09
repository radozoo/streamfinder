import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest';
import { favorites } from './favorites.svelte';

/**
 * Cross-device sync. The network is stubbed here on purpose: these tests are about
 * what the store does with a reply, not about Supabase — the SQL side was smoke
 * tested against the live project when it was created.
 *
 * The cases worth having are the ones that quietly lose favourites: a pairing that
 * half-succeeds, a click made offline, and a deletion that has to stick on the other
 * device instead of being pushed back up by a stale copy.
 */
const SYNC_KEY = 'streamfinder:favorites:sync:v1';
const OUTBOX_KEY = 'streamfinder:favorites:outbox:v1';

/** Replies queued in call order; each entry is what that RPC hands back. */
function stubFetch(replies: Array<{ ok: boolean; body?: unknown; status?: number }>) {
	const calls: Array<{ fn: string; body: Record<string, unknown> }> = [];
	let i = 0;
	globalThis.fetch = vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
		calls.push({
			fn: String(url).split('/rpc/')[1],
			body: JSON.parse(String(init?.body ?? '{}'))
		});
		const r = replies[i++] ?? { ok: true, body: [] };
		return {
			ok: r.ok,
			status: r.status ?? (r.ok ? 200 : 400),
			json: async () => r.body ?? (r.ok ? [] : { message: 'nope' })
		} as Response;
	}) as typeof fetch;
	return calls;
}

const rows = (...ids: number[]) => ids.map((id) => ({ csfd_id: id, created_at: '2026-01-01' }));

beforeEach(() => {
	favorites.unlink();
	favorites.clear();
	localStorage.clear();
});

afterEach(() => {
	vi.restoreAllMocks();
});

describe('sync is off until asked for', () => {
	test('a fresh visitor has it off and nothing stored', () => {
		expect(favorites.syncEnabled).toBe(false);
		expect(favorites.syncState).toBe('off');
		expect(localStorage.getItem(SYNC_KEY)).toBeNull();
	});

	test('hearting a title while off never touches the network', () => {
		const calls = stubFetch([]);
		favorites.toggle(123);
		expect(calls).toEqual([]);
		expect(favorites.has(123)).toBe(true);
	});
});

describe('switching it on', () => {
	test('mints a key, pushes what is already here, and keeps the union', async () => {
		favorites.toggle(1);
		const calls = stubFetch([{ ok: true, body: rows(2, 1) }]);

		await favorites.enableSync();

		expect(calls[0].fn).toBe('sf_favs_merge');
		expect(calls[0].body.p_csfd_ids).toEqual([1]);
		// The server had 2 from another device; joining must not drop it.
		expect(favorites.ids).toEqual([2, 1]);
		expect(favorites.syncEnabled).toBe(true);
		expect(favorites.syncState).toBe('ok');
	});

	test('the key is long enough for the server to accept', async () => {
		stubFetch([{ ok: true, body: [] }]);
		await favorites.enableSync();
		const stored = JSON.parse(localStorage.getItem(SYNC_KEY) ?? '{}');
		// sf_key_ok() enforces `length between 20 and 128` in Postgres.
		expect(stored.key.length).toBeGreaterThanOrEqual(20);
		expect(stored.key.length).toBeLessThanOrEqual(128);
	});

	test('a failed handshake leaves sync OFF rather than half-on', async () => {
		// A device that believes it is syncing while nothing reaches the server is worse
		// than one that is plainly off: the visitor stops making backups.
		stubFetch([{ ok: false, status: 400, body: { message: 'invalid list key' } }]);

		await favorites.enableSync();

		expect(favorites.syncEnabled).toBe(false);
		expect(localStorage.getItem(SYNC_KEY)).toBeNull();
		expect(favorites.syncState).toBe('error');
		expect(favorites.syncError).toContain('invalid list key');
	});

	test('the pairing link carries the key in the fragment, not the query', async () => {
		stubFetch([{ ok: true, body: [] }]);
		await favorites.enableSync();
		const url = favorites.pairingUrl ?? '';
		// A query string would reach the server in access logs and Referer headers.
		expect(url).toMatch(/#sync=[0-9a-f]{32}$/);
		expect(url).not.toContain('?sync=');
	});
});

describe('pairing a second device', () => {
	test('merges instead of overwriting what this device already had', async () => {
		favorites.toggle(9);
		const calls = stubFetch([{ ok: true, body: rows(9, 4) }]);

		await favorites.linkTo('a'.repeat(32));

		expect(calls[0].fn).toBe('sf_favs_merge');
		expect(calls[0].body.p_csfd_ids).toEqual([9]);
		expect(favorites.ids).toEqual([9, 4]);
	});

	test('a key too short to be ours is ignored without a request', async () => {
		const calls = stubFetch([]);
		await favorites.linkTo('short');
		expect(calls).toEqual([]);
		expect(favorites.syncEnabled).toBe(false);
	});
});

describe('a click that could not be sent', () => {
	test('still takes effect locally and waits in the outbox', async () => {
		stubFetch([{ ok: true, body: [] }]);
		await favorites.enableSync();

		stubFetch([{ ok: false, status: 503 }]);
		favorites.toggle(77);
		await vi.waitFor(() => expect(favorites.syncState).toBe('error'));

		expect(favorites.has(77)).toBe(true); // the click is never lost
		const box = JSON.parse(localStorage.getItem(OUTBOX_KEY) ?? '{}');
		expect(box.add).toEqual([77]);
	});

	test('is replayed before the next pull, so it survives the server copy', async () => {
		stubFetch([{ ok: true, body: [] }]);
		await favorites.enableSync();

		stubFetch([{ ok: false, status: 503 }]);
		favorites.toggle(77);
		await vi.waitFor(() => expect(favorites.syncState).toBe('error'));

		// Back online: the queued add goes first, and only then does the list come down.
		const calls = stubFetch([{ ok: true }, { ok: true, body: rows(77) }]);
		await favorites.refresh();

		expect(calls.map((c) => c.fn)).toEqual(['sf_favs_add', 'sf_favs_list']);
		expect(favorites.ids).toEqual([77]);
		expect(JSON.parse(localStorage.getItem(OUTBOX_KEY) ?? '{}').add).toEqual([]);
	});

	test('the outbox keeps only the last intent for a title', async () => {
		stubFetch([{ ok: true, body: [] }]);
		await favorites.enableSync();

		stubFetch([{ ok: false }, { ok: false }]);
		favorites.toggle(5); // add, fails
		await vi.waitFor(() => expect(favorites.syncState).toBe('error'));
		favorites.toggle(5); // remove, fails
		await vi.waitFor(() =>
			expect(JSON.parse(localStorage.getItem(OUTBOX_KEY) ?? '{}').remove).toEqual([5])
		);

		const box = JSON.parse(localStorage.getItem(OUTBOX_KEY) ?? '{}');
		expect(box.add).toEqual([]);
		expect(box.remove).toEqual([5]);
	});
});

describe('deleting on one device', () => {
	test('sticks: a load takes the server copy rather than pushing the stale one back', async () => {
		stubFetch([{ ok: true, body: rows(1, 2, 3) }]);
		await favorites.enableSync();
		expect(favorites.ids).toEqual([1, 2, 3]);

		// The laptop removed 2. This device still has it locally; the pull must win,
		// otherwise the deletion bounces straight back up and never sticks anywhere.
		stubFetch([{ ok: true, body: rows(1, 3) }]);
		await favorites.refresh();

		expect(favorites.ids).toEqual([1, 3]);
		expect(favorites.has(2)).toBe(false);
	});

	test('a server that is unreachable leaves the local list alone', async () => {
		stubFetch([{ ok: true, body: rows(1, 2) }]);
		await favorites.enableSync();

		stubFetch([{ ok: false, status: 500 }]);
		await favorites.refresh();

		expect(favorites.ids).toEqual([1, 2]); // browsing goes on with what it had
		expect(favorites.syncState).toBe('error');
	});
});

describe('unlinking', () => {
	test('stops syncing this device and forgets the key', async () => {
		stubFetch([{ ok: true, body: rows(1) }]);
		await favorites.enableSync();

		favorites.unlink();

		expect(favorites.syncEnabled).toBe(false);
		expect(localStorage.getItem(SYNC_KEY)).toBeNull();
		// The list itself stays — unlinking is not a delete.
		expect(favorites.ids).toEqual([1]);

		const calls = stubFetch([]);
		favorites.toggle(8);
		expect(calls).toEqual([]);
	});
});

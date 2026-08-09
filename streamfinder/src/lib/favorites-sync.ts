/**
 * Transport for cross-device favourites.
 *
 * The catalog is a static build with no backend of its own, so the one thing that
 * has to outlive a single browser — the visitor's own list — is kept in the shared
 * Supabase project (the same one the lunch app uses), in `streamfinder_favs`.
 *
 * WHY RAW fetch AND NOT @supabase/supabase-js. Four RPC calls, each a POST with a
 * JSON body. The client library is ~60 kB gzipped for what fits in this file, and
 * the site is measured against a payload budget (e2e/payload.mjs).
 *
 * WHY THE ANON KEY IS IN THE SOURCE. It is the publishable key and public by
 * design: it grants nothing on its own. `streamfinder_favs` has RLS enabled with no
 * policies at all, so this key cannot read, insert or delete a single row directly
 * — verified against the live project. Everything goes through security-definer
 * functions that demand the list key first. See supabase/streamfinder_favs.sql.
 */

const SUPABASE_URL = 'https://yxanvcrjenmnrrtytbop.supabase.co';
const SUPABASE_ANON_KEY = 'sb_publishable_BerkBlxLuISgdR1WdAwdwQ_J7v1nkAN';

/** Server-side check is `length between 20 and 128`; 32 hex chars is 128 bits of entropy. */
export function newListKey(): string {
	const bytes = crypto.getRandomValues(new Uint8Array(16));
	return Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
}

/** The shape the definer functions hand back: newest first. */
type Row = { csfd_id: number; created_at: string };

async function rpc<T>(fn: string, body: Record<string, unknown>): Promise<T> {
	const res = await fetch(`${SUPABASE_URL}/rest/v1/rpc/${fn}`, {
		method: 'POST',
		headers: {
			apikey: SUPABASE_ANON_KEY,
			'Content-Type': 'application/json'
		},
		body: JSON.stringify(body)
	});
	if (!res.ok) {
		// The body carries Postgres' own message ("invalid list key"), which is far more
		// useful in a bug report than a bare 400.
		let detail = '';
		try {
			detail = ((await res.json()) as { message?: string }).message ?? '';
		} catch {
			// non-JSON error body — the status alone will have to do
		}
		throw new Error(`sync ${fn} failed (${res.status})${detail ? `: ${detail}` : ''}`);
	}
	return (await res.json()) as T;
}

export async function pull(key: string): Promise<number[]> {
	const rows = await rpc<Row[]>('sf_favs_list', { p_key: key });
	return rows.map((r) => r.csfd_id);
}

/**
 * Push this device's list up, get the union back. Used when sync is switched on and
 * on every page load: a device that hearted something while offline must not lose it
 * just because another device wrote in the meantime.
 */
export async function merge(key: string, ids: number[]): Promise<number[]> {
	const rows = await rpc<Row[]>('sf_favs_merge', { p_key: key, p_csfd_ids: ids });
	return rows.map((r) => r.csfd_id);
}

export async function add(key: string, csfdId: number): Promise<void> {
	await rpc<null>('sf_favs_add', { p_key: key, p_csfd_id: csfdId });
}

export async function remove(key: string, csfdId: number): Promise<void> {
	await rpc<null>('sf_favs_remove', { p_key: key, p_csfd_id: csfdId });
}

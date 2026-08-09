import { browser } from '$app/environment';
import * as sync from './favorites-sync';

/**
 * Favourites: the visitor's own watchlist.
 *
 * WHY LOCAL FIRST. The site is a static build on GitHub Pages with no backend, and a
 * favourite here is a private note to self — "I want to watch this" — not something
 * anyone else benefits from seeing. So localStorage is the default and the whole
 * feature works with no account, no server and no network.
 *
 * WHY SYNC IS OPT-IN. The one thing localStorage cannot do is follow you to the
 * phone. That now works, but only once the visitor asks for it: turning it on mints
 * a random secret key and mirrors the list into Supabase under that key. Nobody's
 * watchlist leaves their browser by default. The shape used by the sibling lunch app
 * — identity is a typed name, everything readable by everyone — would be wrong here:
 * on a public site, anyone typing "Rado" would own Rado's list.
 *
 * WHY THE SERVER WINS ON LOAD, ONCE LINKED. Pairing merges the two sides, because a
 * phone that already had hearts must not lose them by joining. After that, every
 * load PULLS: without it, a title deleted on the laptop would be pushed straight
 * back up by the phone's stale copy and no deletion would ever stick. Changes made
 * while offline are not lost to this — they sit in an outbox that is flushed before
 * the pull.
 *
 * WHY csfd_id AND NOT id. `id` in the exported catalog is a local Postgres SERIAL.
 * It works as a URL segment, but it is reassigned if the database is ever rebuilt
 * from scratch — which would silently repoint every saved favourite at a different
 * film. ČSFD's own id never moves, so that is what is stored.
 */
const KEY = 'streamfinder:favorites:v1';
const SYNC_KEY = 'streamfinder:favorites:sync:v1';
const OUTBOX_KEY = 'streamfinder:favorites:outbox:v1';

type Stored = { v: 1; ids: number[] };
type StoredKey = { v: 1; key: string };
/** Toggles made while the network was unavailable, replayed before the next pull. */
type Outbox = { v: 1; add: number[]; remove: number[] };

export type SyncState = 'off' | 'busy' | 'ok' | 'error';

function read(): number[] {
	if (!browser) return [];
	try {
		const raw = localStorage.getItem(KEY);
		if (!raw) return [];
		const parsed = JSON.parse(raw) as Stored;
		// Anything unexpected is treated as "no favourites" rather than throwing on
		// every page load — a corrupt entry must not take the whole site down.
		if (!parsed || parsed.v !== 1 || !Array.isArray(parsed.ids)) return [];
		return parsed.ids.filter((n) => Number.isInteger(n));
	} catch {
		return [];
	}
}

function write(ids: number[]) {
	if (!browser) return;
	try {
		localStorage.setItem(KEY, JSON.stringify({ v: 1, ids } satisfies Stored));
	} catch {
		// Private mode and full quotas both throw here. The in-memory list still works
		// for this session; silently losing persistence beats breaking the click.
	}
}

function readSyncKey(): string | null {
	if (!browser) return null;
	try {
		const raw = localStorage.getItem(SYNC_KEY);
		if (!raw) return null;
		const parsed = JSON.parse(raw) as StoredKey;
		if (!parsed || parsed.v !== 1 || typeof parsed.key !== 'string') return null;
		// Too short to be one of ours, and the server would reject it anyway.
		return parsed.key.length >= 20 ? parsed.key : null;
	} catch {
		return null;
	}
}

function writeSyncKey(key: string | null) {
	if (!browser) return;
	try {
		if (key === null) localStorage.removeItem(SYNC_KEY);
		else localStorage.setItem(SYNC_KEY, JSON.stringify({ v: 1, key } satisfies StoredKey));
	} catch {
		// See write(): losing persistence is survivable, throwing here is not.
	}
}

function readOutbox(): Outbox {
	if (!browser) return { v: 1, add: [], remove: [] };
	try {
		const parsed = JSON.parse(localStorage.getItem(OUTBOX_KEY) ?? '') as Outbox;
		if (!parsed || parsed.v !== 1 || !Array.isArray(parsed.add) || !Array.isArray(parsed.remove)) {
			return { v: 1, add: [], remove: [] };
		}
		return parsed;
	} catch {
		return { v: 1, add: [], remove: [] };
	}
}

function writeOutbox(box: Outbox) {
	if (!browser) return;
	try {
		localStorage.setItem(OUTBOX_KEY, JSON.stringify(box));
	} catch {
		// Same reasoning as write().
	}
}

class FavoriteStore {
	/** Newest first — the order the Oblíbené page lists them in. */
	#ids = $state<number[]>([]);
	#syncKey = $state<string | null>(null);
	#syncState = $state<SyncState>('off');
	#syncError = $state<string | null>(null);

	constructor() {
		// Read in the constructor, NOT lazily from the getter. `has()` is called while
		// $derived expressions evaluate, and assigning state in that phase throws
		// state_unsafe_mutation. During prerender `browser` is false, so the server
		// output simply has no hearts filled and the client fills them on load.
		if (!browser) return;
		this.#ids = read();
		this.#syncKey = readSyncKey();
		if (this.#syncKey) {
			this.#syncState = 'busy';
			// Deliberately not awaited: the list on screen is already correct from
			// localStorage, and the network must never delay the first paint.
			void this.refresh();
		}
		// Another tab is the same person: keep the two in step rather than letting the
		// last one to write win.
		window.addEventListener('storage', (e) => {
			if (e.key === KEY) this.#ids = read();
			if (e.key === SYNC_KEY) this.#syncKey = readSyncKey();
		});
	}

	get ids(): number[] {
		return this.#ids;
	}

	get count(): number {
		return this.ids.length;
	}

	has(csfdId: number | null | undefined): boolean {
		if (csfdId == null) return false;
		return this.ids.includes(csfdId);
	}

	toggle(csfdId: number | null | undefined): boolean {
		if (csfdId == null) return false;
		const wasFav = this.#ids.includes(csfdId);
		const next = wasFav ? this.#ids.filter((n) => n !== csfdId) : [csfdId, ...this.#ids];
		this.#ids = next;
		write(next);
		if (this.#syncKey) void this.#push(csfdId, wasFav ? 'remove' : 'add');
		return next.includes(csfdId);
	}

	clear() {
		this.#ids = [];
		write([]);
	}

	// ── sync ──────────────────────────────────────────────────────────────────

	get syncEnabled(): boolean {
		return this.#syncKey !== null;
	}

	get syncState(): SyncState {
		return this.#syncState;
	}

	get syncError(): string | null {
		return this.#syncError;
	}

	/**
	 * The link that pairs another device. The key rides in the fragment, which browsers
	 * never send to a server — so it stays out of access logs and Referer headers, both
	 * of which would otherwise leak the one secret protecting the list.
	 */
	get pairingUrl(): string | null {
		if (!browser || !this.#syncKey) return null;
		return `${location.origin}${location.pathname}#sync=${this.#syncKey}`;
	}

	/** Switch sync on for the first time: mint a key and push what is already here. */
	async enableSync(): Promise<void> {
		if (!browser || this.#syncKey) return;
		await this.#link(sync.newListKey());
	}

	/**
	 * Join an existing list from a pairing link. Merges rather than pulls: whatever
	 * this device had hearted before pairing must survive joining.
	 */
	async linkTo(key: string): Promise<void> {
		if (!browser || key.length < 20) return;
		if (key === this.#syncKey) return void this.refresh();
		await this.#link(key);
	}

	async #link(key: string): Promise<void> {
		this.#syncState = 'busy';
		this.#syncError = null;
		try {
			const union = await sync.merge(key, this.#ids);
			this.#syncKey = key;
			writeSyncKey(key);
			this.#apply(union);
			this.#syncState = 'ok';
		} catch (err) {
			// The key is NOT saved on failure: a half-linked device that believes it is
			// syncing while nothing reaches the server is worse than one that is plainly off.
			this.#syncState = 'error';
			this.#syncError = err instanceof Error ? err.message : 'Synchronizaci se nepodařilo zapnout';
		}
	}

	/**
	 * Stop syncing this device. The rows stay on the server on purpose — other paired
	 * devices go on working, and re-pairing with the same link brings this one back.
	 */
	unlink() {
		this.#syncKey = null;
		this.#syncState = 'off';
		this.#syncError = null;
		writeSyncKey(null);
		writeOutbox({ v: 1, add: [], remove: [] });
	}

	/** Replay anything that failed to send, then take the server's copy as the truth. */
	async refresh(): Promise<void> {
		const key = this.#syncKey;
		if (!browser || !key) return;
		this.#syncState = 'busy';
		this.#syncError = null;
		try {
			await this.#flush(key);
			this.#apply(await sync.pull(key));
			this.#syncState = 'ok';
		} catch (err) {
			// Local favourites are untouched — the visitor keeps browsing with the list
			// they had, and the next load tries again.
			this.#syncState = 'error';
			this.#syncError = err instanceof Error ? err.message : 'Synchronizace se nezdařila';
		}
	}

	#apply(ids: number[]) {
		this.#ids = ids;
		write(ids);
	}

	async #push(csfdId: number, op: 'add' | 'remove'): Promise<void> {
		const key = this.#syncKey;
		if (!key) return;
		this.#syncState = 'busy';
		try {
			await (op === 'add' ? sync.add(key, csfdId) : sync.remove(key, csfdId));
			this.#syncState = 'ok';
			this.#syncError = null;
		} catch (err) {
			// Offline, or the server said no. The click already took effect locally; parking
			// it in the outbox is what stops a heart pressed on a train from vanishing at the
			// next pull, when the server's copy would otherwise overwrite it.
			this.#queue(csfdId, op);
			this.#syncState = 'error';
			this.#syncError = err instanceof Error ? err.message : 'Změnu se nepodařilo odeslat';
		}
	}

	#queue(csfdId: number, op: 'add' | 'remove') {
		const box = readOutbox();
		// An id can only be in one of the two lists: the last toggle is the intent.
		box.add = box.add.filter((n) => n !== csfdId);
		box.remove = box.remove.filter((n) => n !== csfdId);
		box[op].push(csfdId);
		writeOutbox(box);
	}

	async #flush(key: string): Promise<void> {
		const box = readOutbox();
		if (!box.add.length && !box.remove.length) return;
		for (const id of box.add) await sync.add(key, id);
		for (const id of box.remove) await sync.remove(key, id);
		// Only cleared once every call has gone through; a throw above leaves the outbox
		// intact so the next attempt replays it. Re-sending is harmless — add is an
		// upsert and remove is a no-op on an absent row.
		writeOutbox({ v: 1, add: [], remove: [] });
	}

	// ── backup file ───────────────────────────────────────────────────────────

	/** A file the visitor can keep — the answer to "what if I clear my browser?". */
	exportJson(): string {
		return JSON.stringify({ v: 1, ids: this.ids, exported: new Date().toISOString() }, null, 2);
	}

	/** Merges rather than replaces: importing on a second device should add to it. */
	importJson(text: string): { added: number; total: number } {
		const parsed = JSON.parse(text) as Stored;
		if (!parsed || parsed.v !== 1 || !Array.isArray(parsed.ids)) {
			throw new Error('Nerozpoznaný formát souboru');
		}
		const incoming = parsed.ids.filter((n) => Number.isInteger(n));
		const merged = [...new Set([...incoming, ...this.#ids])];
		const added = merged.length - this.#ids.length;
		this.#ids = merged;
		write(merged);
		// An import is a bulk toggle; the paired devices should see it too.
		if (this.#syncKey) void this.#pushMany(merged);
		return { added, total: merged.length };
	}

	async #pushMany(ids: number[]): Promise<void> {
		const key = this.#syncKey;
		if (!key) return;
		this.#syncState = 'busy';
		try {
			this.#apply(await sync.merge(key, ids));
			this.#syncState = 'ok';
			this.#syncError = null;
		} catch (err) {
			for (const id of ids) this.#queue(id, 'add');
			this.#syncState = 'error';
			this.#syncError = err instanceof Error ? err.message : 'Import se nepodařilo odeslat';
		}
	}
}

export const favorites = new FavoriteStore();

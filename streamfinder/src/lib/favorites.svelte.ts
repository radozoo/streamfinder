import { browser } from '$app/environment';

/**
 * Favourites, kept in the visitor's own browser.
 *
 * WHY LOCAL AND NOT A DATABASE. The site is a static build on GitHub Pages with no
 * backend, and a favourite here is a private note to self — "I want to watch this" —
 * not something anyone else benefits from seeing. A shared, name-keyed store (the
 * shape used by the sibling lunch app) would need a service, and its identity model
 * lets anyone who types your name edit your list. Neither cost buys anything for a
 * personal watchlist, so this is localStorage. The trade-off, stated plainly: the
 * list does not follow you to another device and is lost if browser data is cleared.
 * Export/import below is the escape hatch for both.
 *
 * WHY csfd_id AND NOT id. `id` in the exported catalog is a local Postgres SERIAL.
 * It works as a URL segment, but it is reassigned if the database is ever rebuilt
 * from scratch — which would silently repoint every saved favourite at a different
 * film. ČSFD's own id never moves, so that is what is stored.
 */
const KEY = 'streamfinder:favorites:v1';

type Stored = { v: 1; ids: number[] };

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

class FavoriteStore {
	/** Newest first — the order the Oblíbené page lists them in. */
	#ids = $state<number[]>([]);

	constructor() {
		// Read in the constructor, NOT lazily from the getter. `has()` is called while
		// $derived expressions evaluate, and assigning state in that phase throws
		// state_unsafe_mutation. During prerender `browser` is false, so the server
		// output simply has no hearts filled and the client fills them on load.
		if (!browser) return;
		this.#ids = read();
		// Another tab is the same person: keep the two in step rather than letting the
		// last one to write win.
		window.addEventListener('storage', (e) => {
			if (e.key === KEY) this.#ids = read();
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
		const next = this.#ids.includes(csfdId)
			? this.#ids.filter((n) => n !== csfdId)
			: [csfdId, ...this.#ids];
		this.#ids = next;
		write(next);
		return next.includes(csfdId);
	}

	clear() {
		this.#ids = [];
		write([]);
	}

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
		return { added, total: merged.length };
	}
}

export const favorites = new FavoriteStore();

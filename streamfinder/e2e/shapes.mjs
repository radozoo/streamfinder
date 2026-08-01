/**
 * Pick real titles by DATA SHAPE for the smoke sweep.
 *
 * Not by fame. Every rendering bug this project has had was a shape nobody happened
 * to open while developing: an episode whose ČSFD name is a bare clock time, a work
 * with no genres, a cast of 140 names. "Ted Lasso" exercises one shape; the extremes
 * exercise the ones that actually break.
 *
 * Reads the exported catalog, so the sweep follows the data as it changes instead of
 * pinning ids that rot.
 */
import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';

const DATA = new URL('../static/data/', import.meta.url).pathname;

export function pickShapes() {
	const index = JSON.parse(readFileSync(join(DATA, 'titles_index.json'), 'utf8'));
	const byId = new Map(index.map((t) => [t.id, t]));
	const picks = new Map(); // shape name → title (a Map so one title can't be picked twice)

	const take = (shape, pred, sort) => {
		let cands = index.filter(pred);
		if (sort) cands = cands.sort(sort);
		const hit = cands.find((t) => ![...picks.values()].some((p) => p.id === t.id)) ?? cands[0];
		if (hit) picks.set(shape, hit);
	};

	const num = (v) => v ?? 0;

	// ── shapes visible in the index ────────────────────────────────────────────
	take('serial with most episodes', (t) => t.is_toplevel && t.episode_count > 0,
		(a, b) => num(b.episode_count) - num(a.episode_count));
	take('running serial', (t) => t.is_toplevel && t.is_running);
	take('single episode', (t) => t.is_toplevel === false && t.episode_no != null);
	take('season row', (t) => t.is_toplevel === false && t.season_no != null && t.episode_no == null);
	take('no poster', (t) => !t.poster);
	take('no rating', (t) => t.rating == null);
	take('no votes', (t) => num(t.votes_count) === 0 && t.rating != null);
	take('no platforms', (t) => (t.platforms?.length ?? 0) === 0);
	take('no genres', (t) => (t.genres?.length ?? 0) === 0);
	take('no year', (t) => t.year == null);
	take('oldest', (t) => t.year != null, (a, b) => a.year - b.year);
	take('newest', (t) => t.year != null, (a, b) => b.year - a.year);
	take('longest title', () => true, (a, b) => b.title.length - a.title.length);
	take('non-latin title', (t) => /[Ѐ-ӿ　-鿿֐-׿؀-ۿ]/.test(t.title));
	take('most voted', () => true, (a, b) => num(b.votes_count) - num(a.votes_count));
	take('most genres', () => true, (a, b) => (b.genres?.length ?? 0) - (a.genres?.length ?? 0));
	take('most platforms', () => true, (a, b) => (b.platforms?.length ?? 0) - (a.platforms?.length ?? 0));
	take('inherited rating', (t) => t.rating == null && t.inherited_rating != null);

	// ── shapes that only exist in the detail shards ───────────────────────────
	// Scanning every one of 51k files costs more than the sweep itself, so a spread
	// sample is taken instead: enough to surface an extreme, cheap enough to run.
	const files = readdirSync(join(DATA, 'detail'));
	const step = Math.max(1, Math.floor(files.length / 4000));
	let biggestCast = null,
		mostReviews = null,
		noCrew = null,
		noPlot = null,
		manyEpisodes = null;
	for (let i = 0; i < files.length; i += step) {
		let d;
		try {
			d = JSON.parse(readFileSync(join(DATA, 'detail', files[i]), 'utf8'));
		} catch {
			continue;
		}
		if (!byId.has(d.id)) continue;
		if (!biggestCast || d.actors.length > biggestCast.actors.length) biggestCast = d;
		if (!mostReviews || d.reviews.length > mostReviews.reviews.length) mostReviews = d;
		if (!noCrew && !d.actors.length && !d.directors.length) noCrew = d;
		if (!noPlot && !d.plot) noPlot = d;
		if (!manyEpisodes || (d.episodes?.length ?? 0) > (manyEpisodes.episodes?.length ?? 0))
			manyEpisodes = d;
	}
	const detailShapes = {
		'biggest cast': biggestCast,
		'most reviews': mostReviews,
		'no crew at all': noCrew,
		'no plot': noPlot,
		'longest episode timeline': manyEpisodes
	};
	for (const [shape, d] of Object.entries(detailShapes)) {
		if (d && byId.has(d.id)) picks.set(shape, byId.get(d.id));
	}

	return [...picks].map(([shape, t]) => ({ shape, ...t }));
}

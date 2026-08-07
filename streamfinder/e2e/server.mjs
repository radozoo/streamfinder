/**
 * Start a dev server for an e2e run and make sure it dies with us.
 *
 * Written after eight orphaned dev servers were found pegging a CPU core each. Two
 * separate mistakes caused that, and both are fixed here:
 *
 *   1. `npx vite dev` is a CHAIN of processes — npx spawns npm exec, which spawns the
 *      real node/vite. Killing the handle we hold kills only the first link and
 *      orphans the one doing the work. Spawning `detached: true` puts the whole chain
 *      in its own process group, and killing -pid takes the group down together.
 *
 *   2. `process.on('exit')` never runs when the script is killed from outside (a test
 *      timeout, a Ctrl-C) or dies on an unhandled rejection — which is exactly when
 *      cleanup matters most. Every one of those paths is wired up below.
 *
 * It also picks its own port, because hardcoding one is not safe on a machine with
 * other projects on it. The old version waited until *something* answered the port
 * and took that as success — so when another project's dev server already held it,
 * the suite happily tested that site instead. A crew-facet run spent two minutes
 * timing out on a bikepacking photo journey before the failure text gave it away, and
 * the a11y audit's port was occupied the same way, which would have quietly audited
 * the wrong site rather than failing. Now: find a free port, pass --strictPort so vite
 * refuses to drift to another one, and confirm the thing answering is actually us.
 */
import { spawn } from 'node:child_process';
import { createServer } from 'node:net';
import { createServer as createHttpServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { extname } from 'node:path';

/** Is anything listening here? */
function isFree(port) {
	return new Promise((resolve) => {
		const probe = createServer();
		probe.once('error', () => resolve(false));
		probe.once('listening', () => probe.close(() => resolve(true)));
		probe.listen(port, '127.0.0.1');
	});
}

/**
 * First free port in a range of our own.
 *
 * Deliberately not `listen(0)`: that hands back an ephemeral port, which the OS also
 * draws from for outgoing connections. A run that bound 61086 had its dev server
 * disappear mid-test, which surfaced as ERR_CONNECTION_REFUSED on the second
 * navigation and looked like a crash. A fixed private range stays out of that fight.
 */
async function pickPort() {
	for (let port = 5300; port < 5360; port++) {
		if (await isFree(port)) return port;
	}
	throw new Error('no free port in 5300-5359');
}

/**
 * Serve the production build the way GitHub Pages serves it.
 *
 * Two reasons this is not `vite dev` and not `vite preview`.
 *
 * Not dev: SvelteKit renders the first request on the server there, so a route's
 * `load` fetches happen server-side and never reach the browser's network log. A
 * title page reported "no data files" while it was in fact fetching its detail
 * shard, and every payload budget passed while measuring nothing.
 *
 * Not preview: our non-prerendered routes (Katalóg, Kalendář, every title page) are
 * served through a 404.html SPA fallback. GitHub Pages returns that file for unknown
 * paths and the app boots; `vite preview` does not, so /katalog renders SvelteKit's
 * "404 Not Found" there. Verified against the unmodified checkout — this is preview's
 * behaviour, not a regression — but it makes preview useless for measuring exactly
 * the routes we care about.
 *
 * So: a plain static file server with the fallback rule Pages uses.
 */
export async function startStaticServer() {
	await new Promise((resolve, reject) => {
		const build = spawn('npm', ['run', 'build'], { stdio: 'ignore' });
		build.on('exit', (code) =>
			code === 0 ? resolve() : reject(new Error(`build failed with code ${code}`))
		);
	});

	const root = new URL('../build/', import.meta.url);
	const TYPES = {
		'.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css',
		'.json': 'application/json', '.svg': 'image/svg+xml', '.ico': 'image/x-icon',
		'.png': 'image/png', '.jpg': 'image/jpeg', '.webp': 'image/webp',
		'.woff2': 'font/woff2', '.xml': 'application/xml', '.txt': 'text/plain'
	};

	const port = await pickPort();
	const server = createHttpServer(async (req, res) => {
		const path = decodeURIComponent(new URL(req.url, 'http://x').pathname);
		const candidates = [
			path.endsWith('/') ? path + 'index.html' : path,
			path + '.html',
			path + '/index.html'
		];
		for (const c of candidates) {
			try {
				const body = await readFile(new URL('.' + c, root));
				res.writeHead(200, { 'content-type': TYPES[extname(c)] ?? 'application/octet-stream' });
				return res.end(body);
			} catch {
				/* try the next shape */
			}
		}
		// What Pages does: hand back 404.html and let the SPA route it.
		try {
			const body = await readFile(new URL('./404.html', root));
			res.writeHead(404, { 'content-type': 'text/html' });
			return res.end(body);
		} catch {
			res.writeHead(404).end('not found');
		}
	});

	await new Promise((resolve) => server.listen(port, '127.0.0.1', resolve));
	const origin = `http://localhost:${port}`;
	const stop = () => server.close();
	process.on('exit', stop);
	return { origin, port, stop, tail: () => '', died: () => null };
}

export async function startDevServer(_ignoredLegacyPort) {
	return startServer(['vite', 'dev', '--strictPort', '--port']);
}

async function startServer(argv) {
	const port = await pickPort();
	const origin = `http://localhost:${port}`;
	const server = spawn('npx', [...argv, String(port)], {
		stdio: ['ignore', 'pipe', 'pipe'],
		detached: true
	});

	// Keep the server's own output. When it dies, the browser only reports a refused
	// connection; vite's last words are what actually say why.
	let log = '';
	const record = (buf) => {
		log = (log + buf.toString()).slice(-4000);
	};
	server.stdout.on('data', record);
	server.stderr.on('data', record);

	let exited = null;
	server.on('exit', (code, signal) => {
		exited = signal ? `signal ${signal}` : `code ${code}`;
	});

	let stopped = false;
	const stop = () => {
		if (stopped) return;
		stopped = true;
		try {
			process.kill(-server.pid, 'SIGKILL'); // negative pid = the whole group
		} catch {
			try {
				server.kill('SIGKILL');
			} catch {
				/* already gone */
			}
		}
	};

	process.on('exit', stop);
	for (const sig of ['SIGINT', 'SIGTERM', 'SIGHUP']) {
		process.on(sig, () => {
			stop();
			process.exit(1);
		});
	}
	for (const fatal of ['uncaughtException', 'unhandledRejection']) {
		process.on(fatal, (err) => {
			console.error(`\n${fatal}:`, err);
			stop();
			process.exit(1);
		});
	}

	for (let i = 0; i < 60; i++) {
		if (exited) {
			stop();
			throw new Error(`dev server exited with ${exited} before serving:\n${log}`);
		}
		try {
			// Identity check, not just liveness: dimensions.json is this project's own
			// export, so a stray server on the port cannot pass for ours.
			const res = await fetch(`${origin}/data/dimensions.json`);
			if (res.ok) {
				const dims = await res.json();
				if (dims && typeof dims === 'object' && 'genres' in dims) {
					return { origin, port, stop, tail: () => log, died: () => exited };
				}
				stop();
				throw new Error(`something else is serving ${origin} — not the streamfinder dev server`);
			}
		} catch (err) {
			if (String(err.message).includes('not the streamfinder')) throw err;
			/* not up yet */
		}
		await new Promise((r) => setTimeout(r, 500));
	}
	stop();
	throw new Error(`dev server did not start on ${port}:\n${log}`);
}

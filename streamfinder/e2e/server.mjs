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

export async function startDevServer(_ignoredLegacyPort) {
	const port = await pickPort();
	const origin = `http://localhost:${port}`;
	const server = spawn('npx', ['vite', 'dev', '--port', String(port), '--strictPort'], {
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

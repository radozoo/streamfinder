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
 */
import { spawn } from 'node:child_process';

export async function startDevServer(port) {
	const origin = `http://localhost:${port}`;
	const server = spawn('npx', ['vite', 'dev', '--port', String(port)], {
		stdio: 'ignore',
		detached: true
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
		try {
			if ((await fetch(origin)).ok) return { origin, stop };
		} catch {
			/* not up yet */
		}
		await new Promise((r) => setTimeout(r, 500));
	}
	stop();
	throw new Error(`dev server did not start on ${port}`);
}

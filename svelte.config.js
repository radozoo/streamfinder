import adapter from '@sveltejs/adapter-static';

/** @type {import('@sveltejs/kit').Config} */
const config = {
	compilerOptions: {
		// Force runes mode for the project, except for libraries. Can be removed in svelte 6.
		runes: ({ filename }) => (filename.split(/[/\\]/).includes('node_modules') ? undefined : true)
	},
	kit: {
		adapter: adapter({
			fallback: '404.html'
		}),
		paths: {
			base: process.env.BASE_PATH ?? ''
		},
		prerender: {
			// Only crawl these top-level routes; title detail pages use SPA fallback
			crawl: true,
			entries: ['/', '/katalog', '/kalendar', '/insights'],
			handleHttpError: ({ path, referrer, message }) => {
				if (path.startsWith('/titul/') || (referrer && referrer.includes('/titul/'))) return;
				console.warn(`Prerender warning: ${message}`);
			}
		}
	}
};

export default config;

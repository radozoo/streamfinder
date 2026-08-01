import { sveltekit } from '@sveltejs/kit/vite';
import { playwright } from '@vitest/browser-playwright';
// from vitest/config, not vite — only this one knows the `test` key
import { defineConfig } from 'vitest/config';

export default defineConfig({
	plugins: [sveltekit()],
	test: {
		// Component tests render in a real browser rather than a DOM shim: these
		// assertions are about the text a person actually reads on a card, so the
		// closer the environment is to the real thing, the more they are worth.
		browser: {
			enabled: true,
			provider: playwright(),
			headless: true,
			instances: [{ browser: 'chromium' }]
		},
		include: ['src/**/*.{test,spec}.{js,ts}']
	}
});

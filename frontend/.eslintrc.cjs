/* ESLint config for Ash Nazg frontend.
 *
 * Extends @nextcloud/eslint-config (Nextcloud-canonical rules for Vue 3
 * + TypeScript projects) and adds two project-specific guards required
 * by tasks §12.2 and §12.3:
 *
 *   1. raw `fetch()` and direct `axios` imports are forbidden — use
 *      `@nextcloud/axios`. (§12.2)
 *   2. hardcoded English strings in Vue templates are forbidden — wrap
 *      in `t('ash_nazg', '...')` from `@nextcloud/l10n`. (§12.3)
 *
 * NOTE: this config is committed without lockfile-installed plugins.
 * Run `npm ci --ignore-scripts` once before linting; never `npm install`
 * (per repo-root CLAUDE.md / supply-chain rules).
 */
module.exports = {
	root: true,
	// `@nextcloud/eslint-config/vue3` is the Vue 3 + TypeScript preset.
	// The bare `@nextcloud` preset is Vue 2 + JS only and does NOT
	// configure @typescript-eslint/parser for <script setup> blocks,
	// so .vue files with `lang="ts"` raise "Parsing error: Unexpected
	// token" on TS-only syntax (generic defineProps, typed function
	// signatures, etc.). See node_modules/@nextcloud/eslint-config/vue3.js.
	extends: ['@nextcloud/eslint-config/vue3'],
	rules: {
		// §12.2 — block raw fetch().
		'no-restricted-globals': [
			'error',
			{
				name: 'fetch',
				message: 'Use @nextcloud/axios — never raw fetch().',
			},
		],

		// §12.2 — block direct axios import.
		'no-restricted-imports': [
			'error',
			{
				paths: [
					{
						name: 'axios',
						message: 'Import @nextcloud/axios instead of axios directly.',
					},
				],
			},
		],

		// §12.3 — flag bare English strings in Vue templates.
		// `vue/no-bare-strings-in-template` requires plural/translated form
		// via t() / n(). If the rule is unavailable in the installed
		// version, this becomes a no-op rather than a hard error.
		'vue/no-bare-strings-in-template': 'error',
	},
}

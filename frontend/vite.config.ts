// Vite build config for the Ash Nazg frontend.
//
// Multi-entry: every Nextcloud integration point that needs its own
// bundle declares its entry here. The build outputs to ../host/static
// so the host container ships the assets. A manifest.json tells the
// host's Jinja templates which hashed filename to inject for each
// entry — see task §12.6.

import { fileURLToPath, URL } from 'node:url'
import { resolve } from 'node:path'

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

const HOST_STATIC_DIR = resolve(__dirname, '../host/static')

export default defineConfig({
	plugins: [vue()],
	resolve: {
		alias: {
			'@': fileURLToPath(new URL('./src', import.meta.url)),
		},
	},
	build: {
		outDir: HOST_STATIC_DIR,
		emptyOutDir: true,
		// Write manifest at the root of the output dir, not under .vite/,
		// so the host's admin_settings.py can read host/static/manifest.json
		// without knowing about Vite's internal layout.
		manifest: 'manifest.json',
		sourcemap: true,
		rollupOptions: {
			input: {
				'files-action': resolve(__dirname, 'src/files-action.ts'),
				'admin-settings': resolve(__dirname, 'src/admin-settings-main.ts'),
			},
			output: {
				entryFileNames: 'js/[name]-[hash].js',
				chunkFileNames: 'js/chunk-[name]-[hash].js',
				assetFileNames: 'assets/[name]-[hash][extname]',
			},
		},
	},
})

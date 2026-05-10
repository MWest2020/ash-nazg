/**
 * Ash Nazg — Files action registration.
 *
 * Registers a "Run with Ash Nazg" right-click action on Files entries.
 * Per task §12.4: enabled predicate checks admin + extension + size;
 * exec emits an event on @nextcloud/event-bus and shows a toast.
 *
 * SCAFFOLD: the actual run flow (calling host /run, opening the iframe
 * host) lands in the `wire-dosbox-engine` change. This file only sets
 * up the action surface so the wiring change has a stable place to
 * hook into.
 *
 * API note (@nextcloud/files 4.x): `registerFileAction` takes a plain
 * object matching the `IFileAction` interface. There is no `FileAction`
 * class; every callback receives an `ActionContext` / `ActionContextSingle`.
 */

import {
	registerFileAction,
	type ActionContext,
	type ActionContextSingle,
	type IFileAction,
	type INode,
} from '@nextcloud/files'
import { getCurrentUser } from '@nextcloud/auth'
import { showInfo } from '@nextcloud/dialogs'
import { emit } from '@nextcloud/event-bus'
import { translate as t } from '@nextcloud/l10n'

const APP_ID = 'ash_nazg'

/** Extensions the v1 dosbox-x engine claims it can handle. */
const RUNNABLE_EXTENSIONS = ['exe', 'com', 'bat'] as const

/** Hard ceiling on the binary size offered for execution in v1. */
const MAX_BINARY_SIZE_BYTES = 100 * 1024 * 1024

/** Whether the current user has admin rights — gates the Run action. */
function isCurrentUserAdmin(): boolean {
	// SCAFFOLD: a real implementation queries Nextcloud capabilities.
	// `getCurrentUser()` exposes the user object; admin detection is
	// not standardised across @nextcloud/auth versions, so the wiring
	// change replaces this with a capabilities-API lookup.
	const user = getCurrentUser()
	if (!user) {
		return false
	}
	return Boolean((user as unknown as { isAdmin?: boolean }).isAdmin)
}

/**
 * True if the file's name ends with one of `RUNNABLE_EXTENSIONS`.
 *
 * @param node - The Files-app entry the right-click menu was opened on.
 */
function hasRunnableExtension(node: INode): boolean {
	const name = node.basename.toLowerCase()
	return RUNNABLE_EXTENSIONS.some((ext) => name.endsWith(`.${ext}`))
}

const action: IFileAction = {
	id: 'ash_nazg-run',

	displayName: () => t(APP_ID, 'Run with Ash Nazg'),

	// SVG icon lands in `wire-dosbox-engine`. Empty string is a valid
	// IFileAction icon — it just renders without one.
	iconSvgInline: () => '',

	enabled: (context: ActionContext): boolean => {
		if (!isCurrentUserAdmin()) {
			return false
		}
		if (context.nodes.length !== 1) {
			return false
		}
		const node = context.nodes[0]
		if (!node || !node.size || node.size > MAX_BINARY_SIZE_BYTES) {
			return false
		}
		return hasRunnableExtension(node)
	},

	exec: async (context: ActionContextSingle) => {
		const node = context.nodes[0]
		if (!node) {
			return false
		}

		// MVP DEMO MODE — opens the always-on DOSBox-X engine
		// container's KasmVNC web client in a new browser tab.
		// The host shim's /run dispatcher (real per-session
		// spawn via HaRP, file mount via WebDAV) lands in a
		// later iteration of wire-dosbox-engine.
		const demoUrl = 'https://localhost:16901/vnc.html'
		emit('ash_nazg:run-requested', { path: node.path })

		showInfo(
			t(
				APP_ID,
				'Opening DOSBox-X — accept the self-signed cert, then log in (demo / ash_nazg).',
			),
		)
		// Small delay so the toast is readable before the new tab grabs focus.
		window.setTimeout(() => {
			window.open(demoUrl, '_blank', 'noopener,noreferrer')
		}, 800)

		// `null` signals to the Files app that this action handled its
		// own UX (no further file-list navigation needed).
		return null
	},
}

registerFileAction(action)

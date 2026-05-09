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
 */

import { FileAction, registerFileAction, type Node } from '@nextcloud/files'
import { getCurrentUser } from '@nextcloud/auth'
import { showInfo } from '@nextcloud/dialogs'
import { emit } from '@nextcloud/event-bus'
import { translate as t } from '@nextcloud/l10n'

const APP_ID = 'ash_nazg'

/** Extensions the v1 dosbox-x engine claims it can handle. */
const RUNNABLE_EXTENSIONS = ['exe', 'com', 'bat'] as const

/** Hard ceiling on the binary size offered for execution in v1. */
const MAX_BINARY_SIZE_BYTES = 100 * 1024 * 1024

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

function hasRunnableExtension(node: Node): boolean {
	const name = node.basename.toLowerCase()
	return RUNNABLE_EXTENSIONS.some((ext) => name.endsWith(`.${ext}`))
}

const action = new FileAction({
	id: 'ash_nazg-run',

	displayName: () => t(APP_ID, 'Run with Ash Nazg'),

	// SVG icon lands in `wire-dosbox-engine`. Empty string is a valid
	// FileAction icon — it just renders without one.
	iconSvgInline: () => '',

	enabled: (nodes) => {
		if (!isCurrentUserAdmin()) {
			return false
		}
		if (nodes.length !== 1) {
			return false
		}
		const node = nodes[0]
		if (!node || !node.size || node.size > MAX_BINARY_SIZE_BYTES) {
			return false
		}
		return hasRunnableExtension(node)
	},

	exec: async (node) => {
		showInfo(
			t(
				APP_ID,
				'Ash Nazg dispatcher is not wired yet — coming in the next change.',
			),
		)
		emit('ash_nazg:run-requested', { path: node.path })
		// `null` signals to the Files app that this action handled its
		// own UX (no further file-list navigation needed).
		return null
	},
})

registerFileAction(action)

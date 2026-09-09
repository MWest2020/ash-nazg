/**
 * Ash Nazg — Files action registration.
 *
 * Registers a "Run with Ash Nazg" right-click action on Files entries.
 * The enabled predicate checks admin + extension + size; exec starts
 * a session and navigates to it.
 *
 * exec POSTs to the host's /run through the AppAPI proxy and navigates
 * to the session page. The stream itself is not on that page yet —
 * `streaming-proxy` routes KasmVNC through the proxy.
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
import axios from '@nextcloud/axios'
import { showError } from '@nextcloud/dialogs'
import { translate as t } from '@nextcloud/l10n'
import { generateUrl } from '@nextcloud/router'

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

		// The host dispatches on the file's magic bytes, picks an engine
		// and starts a session; it answers only once the session's VNC
		// server accepts connections, so a 200 here means "running".
		try {
			const { data } = await axios.post(
				generateUrl(`/apps/app_api/proxy/${APP_ID}/run`),
				{ path: node.path },
			)
			window.location.href = generateUrl(
				`/apps/app_api/proxy/${APP_ID}/sessions/${data.session_id}`,
			)
		} catch (error) {
			// Surface what the host said — 415 for an unsupported format,
			// 409 for a file already running, and so on. Never "something
			// went wrong".
			const detail =
				(error as { response?: { data?: { message?: string } } })?.response
					?.data?.message ?? String(error)
			showError(t(APP_ID, 'Could not start the session: {detail}', { detail }))
			return false
		}

		// `null` signals to the Files app that this action handled its
		// own UX (no further file-list navigation needed).
		return null
	},
}

registerFileAction(action)

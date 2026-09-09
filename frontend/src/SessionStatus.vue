<script setup lang="ts">
/*
 * Ash Nazg — session status.
 *
 * What a Run navigates to. The session is already running by the time
 * this renders: `POST /run` returns only after the engine's VNC server
 * accepts connections. What is missing is the picture — KasmVNC reaches
 * the browser once `streaming-proxy` routes it through the AppAPI proxy.
 * Until then this page says what is true and offers to close.
 */

import { ref } from 'vue'

import axios from '@nextcloud/axios'
import { showError, showSuccess } from '@nextcloud/dialogs'
import { translate as t } from '@nextcloud/l10n'

import NcButton from '@nextcloud/vue/components/NcButton'
import NcNoteCard from '@nextcloud/vue/components/NcNoteCard'

import IframeHost from './IframeHost.vue'

const APP_ID = 'ash_nazg'
const ENGINE_NAME = 'dosbox-x'

const sessionId = ref<string>(
	document.getElementById('ash-nazg-session')?.dataset.sessionId ?? '',
)
const closed = ref<boolean>(false)
const closing = ref<boolean>(false)

/**
 * Build a URL to one of the app's own routes through the AppAPI proxy.
 *
 * @param path route path on the app, e.g. `/sessions/abc`
 */
function appUrl(path: string): string {
	// This page is served from /exapps/<appid>/… (see files-action.ts), so
	// its own calls go there too: the app_api proxy would want a Nextcloud
	// requesttoken this bare page does not have.
	return `/exapps/${APP_ID}${path}`
}

/**
 * End this session and say what the host answered if it refuses.
 */
async function closeSession(): Promise<void> {
	closing.value = true
	try {
		await axios.delete(appUrl(`/sessions/${sessionId.value}`))
		closed.value = true
		showSuccess(t(APP_ID, 'Session closed.'))
	} catch (error) {
		// Show what the host actually said; "something went wrong" helps nobody.
		const detail
			= (error as { response?: { data?: { message?: string } } })?.response?.data
				?.message ?? String(error)
		showError(t(APP_ID, 'Could not close the session: {detail}', { detail }))
	} finally {
		closing.value = false
	}
}
</script>

<template>
	<div class="ash-nazg-session">
		<h2>{{ t(APP_ID, 'Ash Nazg session') }}</h2>

		<NcNoteCard v-if="closed" type="success">
			{{ t(APP_ID, 'This session has been closed. You can run the file again.') }}
		</NcNoteCard>

		<IframeHost :session-id="sessionId" :ended="closed" />

		<dl>
			<dt>{{ t(APP_ID, 'Session') }}</dt>
			<dd><code>{{ sessionId }}</code></dd>
			<dt>{{ t(APP_ID, 'Engine') }}</dt>
			<dd>{{ ENGINE_NAME }}</dd>
		</dl>

		<NcButton v-if="!closed" :disabled="closing" @click="closeSession">
			{{ closing ? t(APP_ID, 'Closing…') : t(APP_ID, 'Close session') }}
		</NcButton>
	</div>
</template>

<style scoped>
.ash-nazg-session {
	max-width: 42rem;
	margin: 2rem auto;
	padding: 0 1rem;
}

dl {
	display: grid;
	grid-template-columns: max-content 1fr;
	gap: 0.25rem 1rem;
	margin: 1rem 0;
}

dt {
	font-weight: bold;
}

dd {
	margin: 0;
}
</style>

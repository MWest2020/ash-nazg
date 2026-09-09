<script setup lang="ts">
/*
 * Ash Nazg — the session's screen.
 *
 * KasmVNC's own web client in an iframe. Everything it loads — the page,
 * its assets, the websocket — goes through the app's stream relay, which
 * adds the session's credentials; nothing secret travels in a URL.
 *
 * The URL is deliberately not the `app_api/proxy` one the rest of the app
 * uses. That proxy is a PHP controller and cannot return `101 Switching
 * Protocols`, so the websocket handshake dies in it. `/exapps/<appid>/…`
 * is routed straight to HaRP by the web server in front of Nextcloud and
 * carries the upgrade end to end, with the route's ADMIN level still
 * enforced. Measured; see the streaming-proxy change's design.md.
 */

import { computed, ref } from 'vue'

import { translate as t } from '@nextcloud/l10n'

import NcNoteCard from '@nextcloud/vue/components/NcNoteCard'

const APP_ID = 'ash_nazg'

const props = defineProps<{
	sessionId: string
	ended?: boolean
}>()

const failed = ref<boolean>(false)

const streamUrl = computed(() => {
	const base = `/exapps/${APP_ID}/sessions/${props.sessionId}/stream`
	// `path` is not optional. KasmVNC's client builds its websocket URL
	// from this setting relative to the ORIGIN, defaulting to
	// `websockify` — which lands on Nextcloud's root, where nothing
	// answers, and the client sits on its connect screen without ever
	// attempting a connection. It has to be told the relayed path.
	const path = encodeURIComponent(
		`exapps/${APP_ID}/sessions/${props.sessionId}/stream/websockify`,
	)
	// `resize=scale`, not `remote`: the emulator's screen is a fixed
	// 1280x800 and asking the server to match the iframe would crop it.
	// Scaling fits the whole screen in whatever space the page gives it.
	return `${base}/vnc.html?autoconnect=true&reconnect=true&resize=scale&path=${path}`
})
</script>

<template>
	<div class="ash-nazg-iframe-host">
		<NcNoteCard v-if="ended" type="info">
			{{ t('ash_nazg', 'This session has ended.') }}
		</NcNoteCard>
		<NcNoteCard v-else-if="failed" type="error">
			{{ t('ash_nazg', 'The screen could not be loaded. The session may have ended.') }}
		</NcNoteCard>
		<iframe v-else
			:src="streamUrl"
			:title="t('ash_nazg', 'Session screen')"
			class="ash-nazg-iframe-host__frame"
			allow="clipboard-read; clipboard-write"
			@error="failed = true" />
	</div>
</template>

<style scoped>
.ash-nazg-iframe-host {
	width: 100%;
}

.ash-nazg-iframe-host__frame {
	display: block;
	width: 100%;
	/* The emulator is 1280x800; keep its shape rather than letterboxing
	   it inside a fixed height. */
	aspect-ratio: 16 / 10;
	border: 1px solid var(--color-border);
	border-radius: var(--border-radius);
	background: #000;
}
</style>

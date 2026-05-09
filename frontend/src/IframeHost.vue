<script setup lang="ts">
/*
 * Ash Nazg — placeholder for the KasmVNC iframe host component.
 *
 * SCAFFOLD: renders a labelled placeholder block. The real component
 * (websocket plumbing, KasmVNC client, error overlay) lands in the
 * `streaming-proxy` change. That change adds the @nextcloud/dialogs
 * `showError` import for in-iframe error display — intentionally not
 * pre-imported here (re-exporting from <script setup> is not allowed
 * by Vue 3, and an unused import would itself trip the linter).
 */

import { translate as t } from '@nextcloud/l10n'

defineProps<{
	sessionId: string
	streamUrl: string
}>()
</script>

<template>
	<div class="ash-nazg-iframe-host" data-testid="iframe-host-placeholder">
		<dl class="ash-nazg-iframe-host__meta">
			<dt>{{ t('ash_nazg', 'session') }}</dt>
			<dd>{{ sessionId }}</dd>
			<dt>{{ t('ash_nazg', 'stream') }}</dt>
			<dd>{{ streamUrl }}</dd>
		</dl>
	</div>
</template>

<style scoped>
.ash-nazg-iframe-host {
	display: flex;
	flex-direction: column;
	gap: 8px;
	padding: 16px;
	border: 1px dashed var(--color-border);
	border-radius: var(--border-radius);
	background: var(--color-background-hover);
}

.ash-nazg-iframe-host__meta {
	display: grid;
	grid-template-columns: max-content 1fr;
	column-gap: 12px;
	row-gap: 4px;
	margin: 0;
	font-family: var(--font-face-monospace, monospace);
	font-size: 0.9em;
}

.ash-nazg-iframe-host__meta dt {
	color: var(--color-text-maxcontrast);
}

.ash-nazg-iframe-host__meta dd {
	margin: 0;
}
</style>

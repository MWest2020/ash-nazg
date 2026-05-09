<script setup lang="ts">
/*
 * Ash Nazg — admin settings panel.
 *
 * Per task §11.3: top-level NcSettingsSection rendering placeholder
 * controls. Engine toggle for dosbox-x defaults to disabled (per the
 * `engines` capability spec — newly discovered engines start
 * disabled). Save action is a stub that toasts; persistence wiring
 * lands in a later change.
 *
 * Numeric defaults are sourced from the `engines` capability spec
 * dosbox-x SessionConfig: 1024 MB memory, 900 s idle timeout.
 */

import { ref } from 'vue'

import { showInfo } from '@nextcloud/dialogs'
import { translate as t } from '@nextcloud/l10n'

import NcSettingsSection from '@nextcloud/vue/components/NcSettingsSection'
import NcCheckboxRadioSwitch from '@nextcloud/vue/components/NcCheckboxRadioSwitch'
import NcTextField from '@nextcloud/vue/components/NcTextField'
import NcButton from '@nextcloud/vue/components/NcButton'

const APP_ID = 'ash_nazg'

const dosboxEnabled = ref<boolean>(false)
const memoryLimitMb = ref<number>(1024)
const idleTimeoutSeconds = ref<number>(900)

/** Persist the current settings — stub until storage wiring lands. */
function save(): void {
	// SCAFFOLD: persistence lands in a later change.
	showInfo(t(APP_ID, 'saved (not yet persisted)'))
}

/** POST to /selftest and surface the four-check status — stub until wired. */
function runSelfTest(): void {
	// SCAFFOLD: real wiring hits /selftest on the host.
	showInfo(t(APP_ID, 'self-test not yet wired'))
}
</script>

<template>
	<NcSettingsSection :name="t('ash_nazg', 'Ash Nazg')"
		:description="t('ash_nazg', 'Universal application runtime for Nextcloud Files.')">
		<NcCheckboxRadioSwitch v-model:checked="dosboxEnabled">
			{{ t('ash_nazg', 'Enable DOSBox-X engine') }}
		</NcCheckboxRadioSwitch>

		<NcTextField :value="memoryLimitMb.toString()"
			:label="t('ash_nazg', 'Memory limit (MB)')"
			type="number"
			@update:value="(v: string) => (memoryLimitMb = Number(v))" />

		<NcTextField :value="idleTimeoutSeconds.toString()"
			:label="t('ash_nazg', 'Idle timeout (seconds)')"
			type="number"
			@update:value="(v: string) => (idleTimeoutSeconds = Number(v))" />

		<div class="ash-nazg-actions">
			<NcButton variant="primary" @click="save">
				{{ t('ash_nazg', 'Save') }}
			</NcButton>
			<NcButton @click="runSelfTest">
				{{ t('ash_nazg', 'Test installation') }}
			</NcButton>
		</div>
	</NcSettingsSection>
</template>

<style scoped>
.ash-nazg-actions {
	display: flex;
	gap: 8px;
	margin-top: 16px;
}
</style>

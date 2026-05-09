/**
 * Ash Nazg — admin-settings entry point.
 *
 * Mounts the AdminSettings.vue panel into a div the host's admin page
 * template renders with id `ash-nazg-admin-settings`.
 */

import { createApp } from 'vue'

import AdminSettings from './AdminSettings.vue'

const mountTarget = document.getElementById('ash-nazg-admin-settings')
if (mountTarget) {
	createApp(AdminSettings).mount(mountTarget)
}

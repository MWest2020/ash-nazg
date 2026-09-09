/**
 * Ash Nazg — session page entry point.
 *
 * Mounts SessionStatus.vue into the div the host's session page
 * renders with id `ash-nazg-session`.
 */

import { createApp } from 'vue'

import SessionStatus from './SessionStatus.vue'

const mountTarget = document.getElementById('ash-nazg-session')
if (mountTarget) {
	createApp(SessionStatus).mount(mountTarget)
}

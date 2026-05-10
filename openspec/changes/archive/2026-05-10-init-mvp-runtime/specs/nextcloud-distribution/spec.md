# nextcloud-distribution — delta spec

## ADDED Requirements

### Requirement: Installable via Nextcloud App Store without shell access

An admin SHALL be able to install Ash Nazg entirely through the Nextcloud
web UI (Settings → Apps → discover "Ash Nazg" → click Install). No
command-line access to the Nextcloud server SHALL be required for
installation, configuration, or routine operation.

#### Scenario: Admin installs from App Store

- **GIVEN** an admin user on a Nextcloud 30+ instance with AppAPI 5.x and
  a configured Deploy Daemon (HaRP)
- **WHEN** they navigate to Settings → Apps → search "Ash Nazg" and click
  Install
- **THEN** Nextcloud SHALL pull the host container image from the registry
  declared in `info.xml`
- **AND** AppAPI SHALL register the host container with Nextcloud
- **AND** the app SHALL appear in the admin's Settings → Administration
  sidebar within 60 seconds of clicking Install.

#### Scenario: Install fails gracefully without HaRP

- **GIVEN** a Nextcloud instance with only Docker Socket Proxy (no HaRP)
- **WHEN** admin attempts to install
- **THEN** the install SHALL fail with a clear error message naming HaRP
  as the missing dependency
- **AND** a link to `docs/installation.md` SHALL be shown.

#### Scenario: Uninstall is clean

- **GIVEN** Ash Nazg is installed and has spawned engine containers in the past
- **WHEN** admin clicks Uninstall
- **THEN** the host container SHALL be stopped and removed
- **AND** all engine containers (running or stopped) labeled `app=ash-nazg`
  SHALL be removed
- **AND** any persistent volumes used by Ash Nazg SHALL be removed (with
  user confirmation if they contain data)
- **AND** audit log entries from past executions SHALL remain in
  Nextcloud's audit log (the audit log is not Ash Nazg's data; it's
  Nextcloud's).

### Requirement: info.xml declares all required ExApp metadata

The `appinfo/info.xml` SHALL conform to the Nextcloud App Store schema
for ExApps and include all metadata fields required for App Store
listing.

#### Scenario: Required fields present

- **GIVEN** the `info.xml` file
- **WHEN** validated against `https://apps.nextcloud.com/schema/apps/info.xsd`
- **THEN** validation SHALL pass with no errors
- **AND** the file SHALL declare:
  - `<id>ash-nazg</id>`
  - `<name>` in at least English and Dutch
  - `<summary>` and `<description>` in at least English and Dutch
  - `<version>` following semver
  - `<licence>agpl</licence>`
  - `<author>` with name and email
  - `<category>tools</category>`
  - `<website>`, `<bugs>`, `<repository>` URLs
  - `<screenshot>` entries (minimum 1, ideally 3)
  - `<dependencies><nextcloud min-version="30"/></dependencies>`
  - `<external-app>` block with `<docker-install>` containing
    `<registry>`, `<image>`, `<image-tag>` (pinned, never `latest`)

#### Scenario: External app metadata correct

- **GIVEN** the `<external-app>` block in `info.xml`
- **WHEN** parsed by AppAPI
- **THEN** AppAPI SHALL recognize the declared scopes:
  `FILES`, `AUDIT_LOGS`, `NOTIFICATIONS`
- **AND** the protocol SHALL be `http` (HaRP terminates TLS)
- **AND** the system app entrypoint SHALL be a relative URL path that the
  host container serves (e.g., `/`).

### Requirement: Admin settings page exists and is functional

Ash Nazg SHALL provide an admin settings page accessible via Settings
→ Administration → Ash Nazg. This page is the SOLE configuration
surface; no editing of YAML files or config volumes by hand SHALL be
required for routine operation.

#### Scenario: Settings page accessible to admin

- **GIVEN** an admin user
- **WHEN** they navigate to Settings → Administration → Ash Nazg
- **THEN** the page SHALL render within 3 seconds
- **AND** show the current host container status (running/error/starting)
- **AND** show the list of registered engines with their enabled state
- **AND** show the current resource limits and idle timeout.

#### Scenario: Settings page hidden from non-admin

- **GIVEN** a non-admin user
- **WHEN** they navigate to Settings
- **THEN** "Ash Nazg" SHALL NOT appear in their settings sidebar
- **AND** direct URL access to the admin settings page SHALL return 403.

#### Scenario: Engine toggle persists

- **GIVEN** the dosbox-x engine is enabled
- **WHEN** admin clicks the toggle to disable it and the page confirms
  "saved"
- **THEN** the change SHALL persist across host container restarts
- **AND** subsequent dispatch requests for PE32 binaries SHALL be refused
  per the engines/spec.md disabled-engine scenario.

#### Scenario: Resource limit changes apply to next session

- **GIVEN** memory limit is currently 1024 MB and admin changes it to 512 MB
- **WHEN** admin saves the new value
- **THEN** the change SHALL apply to all subsequently spawned engine containers
- **AND** SHALL NOT affect already-running sessions (they keep their
  original limits until they end naturally).

### Requirement: First-run experience guides the admin

Immediately after install, the admin SHALL be able to verify that Ash
Nazg works without needing to upload any binary first. A "Test
installation" affordance on the settings page SHALL run an internal
self-check.

#### Scenario: Self-check passes on healthy install

- **GIVEN** a freshly installed Ash Nazg with HaRP correctly configured
- **WHEN** admin clicks "Test installation" on the settings page
- **THEN** the self-check SHALL verify:
  - Host container responds to `/health`
  - At least one engine is registered and enabled
  - The Deploy Daemon can spawn a transient test container (no engine,
    just a health-check sidecar) and tear it down within 30 seconds
  - Audit log write succeeds (test event, marked `event: ash_nazg.selftest`)
- **AND** all four checks SHALL be reported with green ticks
- **AND** the admin SHALL see a "Ready to use" banner.

#### Scenario: Self-check fails informatively

- **GIVEN** a misconfigured install (e.g., HaRP not reachable)
- **WHEN** admin clicks "Test installation"
- **THEN** the failing check SHALL show a red X with the actual error
  message returned by the underlying call
- **AND** SHALL link to a relevant docs page or troubleshooting section
- **AND** SHALL NOT fall back to vague text like "something went wrong".

### Requirement: Empty Files state explains usage

The Files-app integration SHALL provide a discoverable empty-state
hint when an admin has Ash Nazg installed but has not yet run any
binary, so that first-time use does not require consulting docs.
The hint MUST be dismissible and SHALL appear at most once per user.

#### Scenario: First-time admin sees a hint

- **GIVEN** an admin who has never used Ash Nazg
- **WHEN** they upload an `.exe` file to Files for the first time
- **THEN** Nextcloud's "new file added" toast SHALL include a hint:
  "This file can be run with Ash Nazg — right-click to try"
  (this hint SHALL appear at most once per user, dismissible)
- **AND** right-clicking the file SHALL show the "Run with Ash Nazg"
  action prominently.

### Requirement: Versioning and update path

Ash Nazg SHALL follow semantic versioning. App Store updates SHALL be
non-destructive to user state.

#### Scenario: Patch version update preserves settings

- **GIVEN** Ash Nazg 1.0.0 is installed with custom resource limits
  and the dosbox-x engine enabled
- **WHEN** admin updates to 1.0.1 via the App Store
- **THEN** the resource limits SHALL be preserved
- **AND** the engine SHALL remain enabled
- **AND** any in-flight sessions SHALL be allowed to complete (or be
  cleanly terminated with a notification, configurable).

#### Scenario: Major version update requires explicit consent

- **GIVEN** Ash Nazg 1.x is installed and 2.0.0 is released
- **WHEN** admin views the App Store update prompt
- **THEN** the update SHALL show a "breaking changes" indicator
- **AND** SHALL link to the migration notes for 2.0
- **AND** SHALL NOT auto-apply, even if Nextcloud is configured for
  auto-updates of apps.

### Requirement: Container images published to public registry

The host and engine container images SHALL be published to a public
OCI registry (GHCR) so the Nextcloud Deploy Daemon can pull them
without authentication.

#### Scenario: Public pull succeeds

- **GIVEN** the manifest `ghcr.io/mwest2020/ash-nazg-host:1.0.0`
- **WHEN** an unauthenticated `docker pull` is attempted
- **THEN** the pull SHALL succeed
- **AND** the image SHALL be multi-arch (amd64 + arm64).

#### Scenario: Image tag in info.xml matches a real published tag

- **GIVEN** the version declared in `info.xml`
- **WHEN** the App Store install runs
- **THEN** the registry SHALL contain the corresponding tagged image
- **AND** CI SHALL prevent merging an `info.xml` version bump if the
  matching image has not been pushed.

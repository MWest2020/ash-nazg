# nextcloud-frontend Specification

## Purpose

What the interface is built from, and why it deliberately looks like Nextcloud
instead of like us.

Every rule here says the same thing in a different place: use the platform's own
components, its own Files API, its own dialogs, its own translation machinery. A
hand-rolled UI inside someone else's app is a thing that breaks on their next
release and looks foreign in the meantime. The one piece that is ours is where
the bundle is served from — the host container — because Nextcloud's CSP will not
have it any other way.

## Requirements

### Requirement: Frontend uses Nextcloud's standard library set

The frontend SHALL use Nextcloud's official npm packages for all
integration with the Nextcloud host application. Custom or alternative
implementations of these concerns SHALL NOT be used.

#### Scenario: Required packages present

- **GIVEN** the frontend `package.json`
- **WHEN** dependencies are listed
- **THEN** the following packages SHALL be present at versions compatible
  with the target Nextcloud version (30+):
  - `@nextcloud/vue` — UI components (NcButton, NcSettingsSection, etc.)
  - `@nextcloud/files` — Files API, file action registration
  - `@nextcloud/router` — URL generation for OCS endpoints
  - `@nextcloud/axios` — HTTP client with CSRF token handling
  - `@nextcloud/dialogs` — toasts, confirmation dialogs, error displays
  - `@nextcloud/auth` — current user, request token
  - `@nextcloud/event-bus` — cross-app event publishing
  - `@nextcloud/l10n` — translation (`t`, `n` functions)
  - `@nextcloud/initial-state` — server-rendered config injection

#### Scenario: Custom HTTP client refused

- **GIVEN** any frontend code making HTTP requests to Nextcloud OCS
  endpoints
- **WHEN** code review or linting runs
- **THEN** direct `fetch()` or raw `axios` imports SHALL be flagged
- **AND** the code SHALL be required to use `@nextcloud/axios` so CSRF
  tokens and base URL handling are correct.

### Requirement: Files action registered via @nextcloud/files API

The "Run with Ash Nazg" action SHALL be registered using the
`registerFileAction()` API from `@nextcloud/files` with a properly
constructed `FileAction` object.

#### Scenario: FileAction object well-formed

- **GIVEN** the file action registration code
- **WHEN** inspected
- **THEN** the registered `FileAction` SHALL have:
  - `id`: `'ash-nazg-run'`
  - `displayName`: a translated string via `t('ash-nazg', 'Run with Ash Nazg')`
  - `iconSvgInline`: an inline SVG (the Ash Nazg ring icon)
  - `enabled`: a function that returns `true` only when:
    1. The current user is in the admin group
    2. The file's mime type or extension matches a runnable format
    3. The file size is within the configured limit
  - `exec`: an async function that POSTs to the host's `/run` endpoint
    via `@nextcloud/axios`
  - `order`: a value placing it below default actions but above destructive
    ones (e.g., `10`)

#### Scenario: Action invocation uses event bus for telemetry

- **WHEN** the action's `exec` function is called
- **THEN** before posting to `/run`, an event SHALL be emitted on the
  `@nextcloud/event-bus` with name `ash-nazg:run-requested` and payload
  `{ fileId, mimeType }`
- **AND** other Nextcloud apps SHALL be able to observe this event
  (enables future integrations).

### Requirement: Admin settings rendered with NcSettingsSection

The admin settings page SHALL be rendered using `@nextcloud/vue`'s
`NcSettingsSection` component as the top-level container, conforming to
Nextcloud's settings-page visual conventions.

#### Scenario: Settings page structure

- **GIVEN** the admin settings Vue component
- **WHEN** rendered
- **THEN** the root element SHALL be `<NcSettingsSection>` with:
  - `name` prop: translated "Ash Nazg"
  - `description` prop: translated one-liner explaining the app
  - `doc-url` prop: link to the user-guide on the project site
  - children: the actual configuration form
- **AND** the form SHALL use `NcCheckboxRadioSwitch` for engine
  toggles, `NcTextField` with `type="number"` for limits, and
  `NcButton` for actions like "Test installation".

#### Scenario: Settings page uses initial state

- **GIVEN** the settings page loads
- **WHEN** the Vue component mounts
- **THEN** initial config values SHALL be read via
  `loadState('ash-nazg', 'config')` from `@nextcloud/initial-state`
- **AND** SHALL NOT be fetched via a separate XHR on mount (avoids
  flash of empty state).

### Requirement: Errors displayed via @nextcloud/dialogs

User-facing errors from the host SHALL be displayed using
`@nextcloud/dialogs`' `showError`, `showWarning`, or `showSuccess`
functions, not custom UI.

#### Scenario: Dispatch failure shows toast

- **GIVEN** the user clicks "Run with Ash Nazg" on an unsupported file
- **WHEN** the host returns 415
- **THEN** the frontend SHALL call `showError(t('ash-nazg', 'This file
  type is not supported by any enabled engine'))`
- **AND** SHALL NOT render a custom error component or alert.

#### Scenario: Long-running confirmation uses dialog

- **GIVEN** the admin clicks "Uninstall" or "Reset configuration"
- **WHEN** confirmation is needed
- **THEN** the frontend SHALL use `getDialogBuilder()` from
  `@nextcloud/dialogs` to render a confirmation
- **AND** SHALL NOT use the browser's native `confirm()`.

### Requirement: All user-facing strings translatable

All user-facing strings SHALL be wrapped in a translation function
from `@nextcloud/l10n`. This applies to every string visible to a
user, including button labels, toast messages, settings descriptions,
and the file action display name. The translation function MUST be
either `t(appId, source)` for single strings or
`n(appId, singular, plural, count)` for plural-aware strings.
Strings rendered without a translation wrapper SHALL be treated as a
build error.

#### Scenario: Translation files exist

- **GIVEN** the repository
- **WHEN** the `l10n/` directory is inspected
- **THEN** at minimum English (`en.json`) and Dutch (`nl.json`) SHALL
  exist
- **AND** the build SHALL fail if translation keys appear in source
  but are missing from `en.json`.

#### Scenario: Hardcoded English strings refused

- **GIVEN** any Vue template or TypeScript source file
- **WHEN** linted
- **THEN** literal English strings inside JSX/template attributes that
  render text (e.g., `<NcButton>Save</NcButton>`) SHALL be flagged
- **AND** the lint rule SHALL require wrapping in `t()`.

### Requirement: Frontend bundle served by host container

The compiled frontend bundle SHALL be served by the Ash Nazg host
container from a path declared in `info.xml`. The frontend SHALL NOT
require its own deployment surface.

#### Scenario: Frontend served from host container

- **GIVEN** the host container is running
- **WHEN** Nextcloud loads the Files-app integration script
- **THEN** the request SHALL be proxied via AppAPI to the host
  container's static-asset path (e.g., `/static/files-action.js`)
- **AND** the host container SHALL respond with the correct
  `Content-Type: application/javascript`.

#### Scenario: Bundle versioned with host container

- **GIVEN** a release of host container `1.0.1`
- **WHEN** the image is built
- **THEN** the frontend bundle inside the image SHALL be the matching
  `1.0.1` build of the frontend source
- **AND** the URL SHALL include a cache-busting query parameter or
  fingerprint so Nextcloud doesn't serve stale assets after an update.

### Requirement: The session's screen is visible in Nextcloud

A running session's screen SHALL be visible inside Nextcloud, in the
session page, through the AppAPI proxy — never through a port the
administrator has to expose separately. The stream SHALL reach the
browser over the same single door as every other route of this app.

The app SHALL relay the stream itself: AppAPI allocates one port per
ExApp and the sessions listen behind it, so nothing else can bridge the
two. The relay SHALL forward bytes only; it SHALL NOT reimplement the
VNC client or the RFB protocol, and the iframe SHALL load KasmVNC's own
web client.

#### Scenario: A started session shows its screen

- **GIVEN** an admin has started a session from the Files action
- **WHEN** the session page loads
- **THEN** the page SHALL show the emulator's screen in an iframe served
  through the AppAPI proxy.

#### Scenario: A closed session does not leave a broken frame

- **GIVEN** a session that has been closed or has expired
- **WHEN** its session page is open or reopened
- **THEN** the page SHALL state that the session has ended, rather than
  render a failing iframe.

### Requirement: A session stream is reachable only by its owner

The stream route SHALL authorise the caller before forwarding any byte:
the caller SHALL be an admin, as for `/run`, and SHALL own the session.
A session id SHALL NOT be a capability on its own.

A request for a session that does not exist, and a request for another
caller's session, SHALL both answer 404 — an authorisation error that
distinguishes the two turns the endpoint into an oracle for guessing
session ids.

#### Scenario: Another admin's session is not reachable

- **WHEN** an admin requests the stream of a session started by someone
  else
- **THEN** the app SHALL answer 404 and forward nothing.

#### Scenario: Authorisation precedes the upgrade

- **WHEN** a websocket upgrade is requested on the stream route
- **THEN** the app SHALL complete its authorisation check before the
  connection is upgraded, not after.

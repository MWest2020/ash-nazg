# engines Specification

## Purpose
TBD - created by archiving change init-mvp-runtime. Update Purpose after archive.
## Requirements
### Requirement: Engines implement a stable Engine protocol

Every engine SHALL implement the `Engine` Python protocol defined in the
host package. Adding a new engine SHALL NOT require modifying the host
container's source — engines register via the `ash_nazg.engines`
entrypoint group.

#### Scenario: Engine registration discovered at startup

- **GIVEN** a Python package installed in the host container that declares
  an `ash_nazg.engines` entrypoint
- **WHEN** the host container starts
- **THEN** the host SHALL discover the engine and add it to the dispatch
  registry
- **AND** the engine SHALL appear in the admin settings list of available
  engines.

#### Scenario: Engine missing required methods refused

- **GIVEN** a package that declares the entrypoint but lacks `can_handle`
  or `session_config`
- **WHEN** the host starts
- **THEN** the host SHALL log a warning naming the broken engine
- **AND** SHALL NOT register it
- **AND** SHALL continue starting normally with the remaining engines.

### Requirement: Engines are admin-configurable

Each engine in the registry SHALL be individually enable-able and
disable-able by an admin via the Nextcloud admin settings page.
Disabled engines SHALL NOT be considered during dispatch.

#### Scenario: Disabled engine ignored

- **GIVEN** the dosbox-x engine is registered but admin has disabled it
- **WHEN** a user dispatches a PE32 binary
- **THEN** the host SHALL behave as if no engine handles PE32
- **AND** return 415 with message "no enabled engine handles this format".

#### Scenario: Default state of newly discovered engine

- **GIVEN** the host has just been upgraded and now discovers a new engine
  (e.g., wine added in v2)
- **WHEN** the host starts for the first time after upgrade
- **THEN** the new engine SHALL be registered as DISABLED by default
- **AND** the admin SHALL receive a Nextcloud notification stating "new
  Ash Nazg engine available: <name> — review and enable in admin
  settings".

### Requirement: dosbox-x engine ships in v1

The repository SHALL ship one engine implementation: `dosbox-x`. This
engine SHALL handle binaries detected as `pe32` (Windows .exe) and
`mz-dos` (DOS .exe / .com).

#### Scenario: dosbox-x advertises supported formats

- **WHEN** the host queries `dosbox-x.can_handle()` for various inputs
- **THEN** it SHALL return True for `pe32` and `mz-dos`
- **AND** False for `elf`, `wasm`, `jar`, `mach-o`, `unknown`.

#### Scenario: dosbox-x produces a valid session config

- **GIVEN** a PE32 file at Files path `/Programs/keen1.exe`
- **WHEN** the host calls `dosbox-x.session_config(file_meta)`
- **THEN** the returned `SessionConfig` SHALL contain:
  - `image`: a fully qualified OCI reference (no `:latest`)
  - `cpu_limit`: 1.0
  - `memory_limit_mb`: 1024
  - `mount_path`: `/mnt/files` (the WebDAV mount inside the engine)
  - `streaming_protocol`: `kasmvnc`
  - `streaming_port`: 6901
  - `idle_timeout_seconds`: 900 (15 minutes)
  - `entrypoint_args`: command-line invoking dosbox-x with the resolved
    file path within `/mnt/files`.

### Requirement: Engine images use pinned tags, never :latest

OCI references in engine session configs SHALL use immutable tags
(semver or sha256 digest). The host SHALL refuse to start a container
referencing an engine image with tag `latest` or no tag at all.

#### Scenario: Latest tag refused

- **GIVEN** an engine session config with image
  `ghcr.io/example/engine:latest`
- **WHEN** the host attempts to spawn the container
- **THEN** the host SHALL fail fast with error "engine images must use
  pinned tags"
- **AND** the failure SHALL be logged as an audit event.

### Requirement: One engine container per session

The host SHALL spawn a fresh engine container for every Run request.
Containers SHALL NOT be reused across sessions, even for the same user
and same binary.

#### Scenario: Sequential runs each get fresh containers

- **GIVEN** a user runs `keen1.exe`, closes the session, then runs
  `keen1.exe` again
- **WHEN** the second run starts
- **THEN** a new engine container SHALL be spawned with a new container
  ID
- **AND** the previous container's filesystem state SHALL NOT influence
  the new session.

### Requirement: Engine session lifecycle bounded

Engine containers SHALL be terminated under any of these conditions:

1. User explicitly closes the session via the frontend.
2. Idle timeout reached (configurable, default 900 seconds).
3. Maximum session duration reached (configurable, default 4 hours).
4. Host container is shut down or restarted.

#### Scenario: Idle timeout enforced

- **GIVEN** an engine container running for 14 minutes 59 seconds with
  no websocket activity
- **WHEN** one more second passes with no input
- **THEN** the host SHALL send SIGTERM to the engine container
- **AND** wait 30 seconds for graceful shutdown
- **AND** then SIGKILL if still running.

#### Scenario: Host restart cleans up engines

- **GIVEN** three engine containers running when the host container
  restarts
- **WHEN** the host comes back up
- **THEN** the host SHALL detect orphaned containers (labeled
  `app=ash-nazg`) and stop them
- **AND** SHALL NOT attempt to reattach to their sessions.


# engines Specification

## Purpose

The contract every runtime engine keeps, so that adding one is a drop-in rather
than a refactor.

The MVP ships exactly one engine (dosbox-x), and the reason this capability
exists anyway is that "one engine" is a choice we intend to outgrow. Everything
that is specific to DOS lives behind a protocol: an engine is an independently
versioned OCI image on a pinned tag, it is admin-configurable, it gets one
container per session, and that session has a bounded life. Wine, RetroArch, a
JVM — those are new images against this protocol, not a new host.

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

### Requirement: Engine session lifecycle bounded

Engine sessions SHALL be terminated under any of these conditions:

1. The user closes the session (`DELETE /sessions/{id}`).
2. Maximum session duration reached (configurable, default 4 hours).
3. Host container is shut down or restarted.

Termination SHALL send SIGTERM, wait 30 seconds for the process tree to
exit, and then SIGKILL. It SHALL remove the session's directory and
SHALL release the (user, file) claim that makes a second Run of the same
file return 409 — a session that ends without releasing its claim would
lock the user out of that file for the life of the host.

Idle-based termination SHALL apply: the stream passes through the host's
own relay, which reports per-session activity, so the idle window is
measured where it is actually observable rather than guessed.

#### Scenario: Maximum duration enforced

- **GIVEN** a session that has run for its configured maximum duration
- **WHEN** that moment passes
- **THEN** the host SHALL terminate the session
- **AND** SHALL release its claim, so the same file can be run again.

#### Scenario: Idle timeout enforced

- **GIVEN** a session that has carried no stream traffic in either
  direction for the configured idle window
- **WHEN** the window elapses
- **THEN** the host SHALL terminate the session the same way an explicit
  close does, releasing its claim.

#### Scenario: Host restart cleans up engines

- **GIVEN** sessions running when the host shuts down
- **WHEN** the host process stops
- **THEN** it SHALL terminate every session it started
- **AND** SHALL NOT attempt to reattach to them on the next start.

### Requirement: One engine session per Run, never reused

The host SHALL start a fresh engine process tree for every Run request,
in a private per-session directory, and SHALL NOT reuse a session across
Run requests — not even for the same user and the same binary.

#### Scenario: Sequential runs each get a fresh session

- **GIVEN** a user runs `keen1.exe`, closes the session, then runs
  `keen1.exe` again
- **WHEN** the second run starts
- **THEN** a new session SHALL be started with a new session id and a new
  session directory
- **AND** the previous session's directory SHALL have been removed, so
  its state cannot influence the new session.

#### Scenario: Concurrent sessions are bounded

- **GIVEN** the configured maximum number of concurrent sessions is
  already running
- **WHEN** another Run request arrives
- **THEN** the host SHALL refuse it with a message naming the limit,
  rather than starting a session it cannot isolate.

### Requirement: The engine ships in the ExApp image, pinned

The engine SHALL be part of the ExApp image rather than a separately
spawned container image. `appinfo/info.xml` SHALL pin that image with a
concrete `<image-tag>`, never `latest` — the tag is what an admin
installs and what an audit points at.

#### Scenario: Latest tag refused

- **GIVEN** `appinfo/info.xml` with `<image-tag>latest</image-tag>`
- **WHEN** the image manifest check runs
- **THEN** it SHALL fail with "engine images must use pinned tags".

#### Scenario: The engine is present in the image

- **WHEN** the host's self-test runs its `engine-runtime` check
- **THEN** it SHALL verify that the emulator and the VNC server are
  present in this image and that a session slot is free
- **AND** SHALL report the missing binary by name if either is absent.

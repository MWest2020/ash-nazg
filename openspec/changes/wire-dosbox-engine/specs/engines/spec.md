# Engines — spec deltas

The sibling-container model these requirements assumed does not exist for
an ExApp: it has no docker CLI, no socket, and HaRP offers ExApps no
spawn API. The engine therefore ships inside the ExApp image and a
session is a process tree. See `design.md`, *Decision: the engine ships
in the host image*.

## MODIFIED Requirements

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

Idle-based termination SHALL apply once the streaming layer reports
per-session activity; the host cannot observe websocket traffic that
does not pass through it, and inventing an idle signal it does not have
would be worse than not claiming one.

#### Scenario: Maximum duration enforced

- **GIVEN** a session that has run for its configured maximum duration
- **WHEN** that moment passes
- **THEN** the host SHALL terminate the session
- **AND** SHALL release its claim, so the same file can be run again.

#### Scenario: Host restart cleans up sessions

- **GIVEN** sessions running when the host shuts down
- **WHEN** the host process stops
- **THEN** it SHALL terminate every session it started
- **AND** SHALL NOT attempt to reattach to them on the next start.

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

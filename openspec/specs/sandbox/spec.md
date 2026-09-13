# sandbox Specification

## Purpose

The boundaries around running someone else's binary, and who is allowed to.

This is the part of the app that has to be boring. Execution is admin-only in v1;
a container gets one CPU, a gigabyte and a read-only root; nothing is bundled
that we do not have the right to ship; every run leaves an audit entry saying who
ran which sha256, when, and how it ended; and the token an engine holds reaches
that session's files and nothing else. None of this is clever, and that is the
requirement.

## Requirements

### Requirement: Admin-only execution in v1

Run requests SHALL be accepted only from users with Nextcloud admin
group membership. The host SHALL re-validate admin status on every
Run request, independent of any frontend gating.

#### Scenario: Non-admin user blocked at API

- **GIVEN** a non-admin user whose frontend somehow shows the Run action
- **WHEN** they POST `/run` to the host
- **THEN** the host SHALL return 403 Forbidden
- **AND** log the attempt as an audit event with outcome=forbidden.

#### Scenario: Admin user permitted

- **GIVEN** a user in the Nextcloud admin group
- **WHEN** they POST `/run` for a supported binary
- **THEN** the host SHALL proceed with dispatch.

### Requirement: Audit log entry per execution

The host SHALL write an audit log entry to Nextcloud's audit log via
the OCS API for every Run request, regardless of outcome.

#### Scenario: Successful execution audit entry

- **GIVEN** an admin runs `keen1.exe` and closes the session normally
- **WHEN** the session ends
- **THEN** an audit log entry SHALL exist containing:
  - `event`: `ash_nazg.execution`
  - `user_id`: the Nextcloud user id
  - `file_path`: the Files path
  - `file_sha256`: hex digest of the binary
  - `engine`: engine id
  - `engine_image`: full OCI reference of the spawned image
  - `session_id`: a UUID
  - `started_at`, `ended_at`: ISO8601 timestamps
  - `exit_status`: one of `graceful_close`, `idle_timeout`,
    `max_duration`, `killed_oom`, `killed_admin`, `error`
  - `peak_memory_mb`: integer
  - `cpu_seconds`: float

#### Scenario: Failed dispatch still audited

- **GIVEN** a user attempts to run an unsupported binary
- **WHEN** the host returns 415
- **THEN** an audit log entry SHALL exist with `outcome=refused` and
  `reason` populated, and SHALL NOT have `engine_image` or `session_id`.

### Requirement: No bundled non-open-source content

The repository and all published container images SHALL contain only
software under OSI-approved open source licenses. Proprietary
binaries, ROMs, OS installation images, BIOS files, and proprietary
fonts MUST NOT be included in any image, archive, or git-tracked
artifact under any circumstances. Distribution of user-supplied
proprietary content remains the user's responsibility, never the
project's.

#### Scenario: Win 3.11 image not shipped

- **GIVEN** the dosbox-x engine container image
- **WHEN** its filesystem is inspected
- **THEN** it SHALL NOT contain any Microsoft Windows installation
  files, system files, or fonts
- **AND** the image SHALL NOT contain any pre-configured DOSBox-X
  profile that references such files.

#### Scenario: Documentation directs user to bring their own

- **GIVEN** a user installs the Ash Nazg app
- **WHEN** they read the user guide
- **THEN** the guide SHALL include a section "bring your own software"
  explaining that legacy OS images, ROMs, and proprietary binaries
  must be supplied by the user from their own legally-obtained sources.

### Requirement: Per-session token scoping

The token passed from host to engine container SHALL be scoped to:

1. WebDAV access for the requesting user only
2. Read access to the directory containing the binary
3. Read+write access to the same directory for output

#### Scenario: Token cannot read other users' files

- **GIVEN** admin Alice runs a binary in her Files
- **WHEN** the engine container attempts WebDAV access to `/u/bob/...`
- **THEN** the request SHALL fail with 403
- **AND** an audit log entry SHALL note the attempted out-of-scope access.

#### Scenario: Token expires with session

- **GIVEN** an engine container is terminated (any reason)
- **WHEN** the token is later replayed
- **THEN** AppAPI SHALL reject the token as expired.

### Requirement: Session viewing credentials are per session

The VNC server's credentials SHALL be generated per session and SHALL
live only in that session's private directory. A credential baked into
the image SHALL NOT be used: it is identical for every session and every
installation, and it survives redeployment.

The credential SHALL be gone when the session ends, together with the
session directory, and SHALL NOT appear in any URL that a browser
history, a proxy log or a referrer header could keep.

#### Scenario: Two sessions do not share a credential

- **GIVEN** two sessions running at the same time
- **WHEN** their credentials are compared
- **THEN** they SHALL differ.

#### Scenario: The credential dies with the session

- **WHEN** a session is closed or expires
- **THEN** its credential SHALL no longer grant access to anything.

### Requirement: An unwatched session is terminated

A session SHALL be terminated when no one is watching it for the
configured idle window (default 900 seconds). Activity SHALL be measured
where it is actually observable — the relay through which the stream
passes — and SHALL NOT be inferred from anything the app cannot see.

Idle termination SHALL use the same path as an explicit close, including
release of the (user, file) claim, so that the two cannot disagree about
what a terminated session leaves behind.

#### Scenario: Nobody watching

- **GIVEN** a session whose stream has carried no traffic in either
  direction for the idle window
- **WHEN** the window elapses
- **THEN** the app SHALL terminate the session and release its claim.

#### Scenario: Watching keeps it alive

- **GIVEN** a session someone is watching
- **WHEN** the idle window elapses since the session started
- **THEN** the session SHALL keep running, because traffic reset the
  clock.

### Requirement: Session resources are bounded by what the runtime offers

Every session SHALL be bounded by the strongest mechanism the deployment
actually provides, and the host SHALL NOT claim a bound it does not
enforce.

For in-image sessions that means: a private session directory, a cap on
concurrent sessions, a scheduling priority below the shim's, and a
maximum session duration. It does NOT include cgroup memory or CPU
limits — a process in the ExApp container cannot place itself in a
cgroup, and an RLIMIT big enough for an X server is not a limit worth
the name. A deployment that needs hard resource isolation runs each
engine as its own ExApp, where AppAPI spawns the container and the
daemon applies the limits.

#### Scenario: Concurrency is capped

- **GIVEN** the configured maximum of concurrent sessions is reached
- **WHEN** another Run arrives
- **THEN** the host SHALL refuse it rather than start an unbounded number
  of emulators.

#### Scenario: A session cannot starve the shim

- **GIVEN** a session consuming as much CPU as it can get
- **WHEN** the shim serves a request
- **THEN** the shim SHALL remain responsive, because sessions run at a
  lower scheduling priority.

### Requirement: A session writes only inside its own directory

Each session SHALL receive a private directory, created with mode 0700,
holding the binary to run and nothing else from the user's Files. The
directory SHALL be removed when the session ends. The binary SHALL be
downloaded into it rather than mounted, so a session sees the one file
it was asked to run and no WebDAV mount privileges are needed.

The ExApp's root filesystem is NOT read-only: it is the same filesystem
the shim runs from. That is the cost of the in-image model, and the
route back to a read-only root is a per-engine ExApp.

#### Scenario: The session sees one file

- **GIVEN** a user with many files who runs one of them
- **WHEN** the session starts
- **THEN** the session directory SHALL contain only that binary
- **AND** the session SHALL have no mount of the user's Files.

#### Scenario: Session directory removed on close

- **GIVEN** a session that is closed or expires
- **WHEN** termination completes
- **THEN** the session directory and its contents SHALL be gone.

### Requirement: The emulator is the isolation boundary for in-image sessions

The isolation between an untrusted binary and the host SHALL be the
emulator itself where the session runs inside the ExApp container: the
binary SHALL be a DOS program executed by DOSBox-X, never native code on
the container's CPU. The host SHALL NOT present this as container
isolation.

The consequence SHALL be documented for administrators: a session
process runs under the same uid as the shim, so a compromise of the
emulator process — not of the DOS program it runs, but of DOSBox-X
itself — reaches the shim's environment, including `APP_SECRET`. The
host SHALL keep its own variables out of the session's environment as
hygiene, while not claiming that as a boundary.

#### Scenario: The session environment carries no app secret

- **WHEN** the host starts a session
- **THEN** the child process environment SHALL contain only what the
  engine needs (its file, display, port, and paths)
- **AND** SHALL NOT contain `APP_SECRET` or the other AppAPI variables.

#### Scenario: An admin can see the boundary before installing

- **WHEN** an administrator reads the installation documentation
- **THEN** it SHALL state that sessions run inside the ExApp container
  and what that means for isolation.

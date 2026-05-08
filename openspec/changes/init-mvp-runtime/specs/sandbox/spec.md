# sandbox — delta spec

## ADDED Requirements

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

### Requirement: Resource limits enforced at container level

Every engine container SHALL be spawned with cgroup-enforced resource
limits. The host SHALL pass these limits via Docker run flags or
equivalent OCI runtime configuration.

#### Scenario: Memory limit enforced

- **GIVEN** an engine session config with `memory_limit_mb: 1024`
- **WHEN** the host spawns the container
- **THEN** the container SHALL be started with `--memory=1024m
  --memory-swap=1024m` (no swap allowance)
- **AND** the container SHALL be killed by the kernel OOM-killer if it
  exceeds the limit, not allowed to swap.

#### Scenario: CPU limit enforced

- **GIVEN** an engine session config with `cpu_limit: 1.0`
- **WHEN** the host spawns the container
- **THEN** the container SHALL be started with `--cpus=1.0`.

#### Scenario: No host network exposed

- **GIVEN** any engine session
- **WHEN** the container starts
- **THEN** the container SHALL NOT have access to the host network
- **AND** SHALL only have access to the AppAPI proxy network for
  websocket exposure
- **AND** outbound network from the engine SHALL be blocked unless
  explicitly enabled per-engine in admin config (off by default).

### Requirement: Read-only root filesystem

Engine containers SHALL run with a read-only root filesystem. Writable
surfaces SHALL be limited to:

1. `/tmp` — tmpfs, default 256 MB
2. `/mnt/files` — the user's WebDAV mount
3. Any engine-specific scratch path declared in the session config
   (e.g., DOSBox-X may need `/var/lib/dosbox-x` writable for save state)

#### Scenario: Root filesystem read-only

- **GIVEN** any engine container
- **WHEN** the engine's process attempts to write to `/etc` or `/usr`
- **THEN** the write SHALL fail with EROFS.

### Requirement: Audit log entry per execution

The host SHALL write an audit log entry to Nextcloud's audit log via
the OCS API for every Run request, regardless of outcome.

#### Scenario: Successful execution audit entry

- **GIVEN** an admin runs `keen1.exe` and closes the session normally
- **WHEN** the session ends
- **THEN** an audit log entry SHALL exist containing:
  - `event`: `ash-nazg.execution`
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

The repository, the host container image, and the engine container
image SHALL NOT include any binaries, ROMs, OS images, BIOS files, or
fonts that are not under an OSI-approved open source license.

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

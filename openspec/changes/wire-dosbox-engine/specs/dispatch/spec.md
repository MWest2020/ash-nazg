# Dispatch — spec deltas

## ADDED Requirements

### Requirement: Dispatcher selects first registered enabled engine that handles the file

The dispatcher SHALL iterate over the engine registry in
registration order, calling `can_handle(file_meta)` on each
enabled engine, and SHALL spawn an engine container using the
first engine whose `can_handle()` returns True.

#### Scenario: PE32 file dispatches to dosbox-x

- **GIVEN** the dosbox-x engine is registered and enabled
- **AND** a file at Files path `/Programs/keen1.exe` whose
  magic-byte family is `pe32`
- **WHEN** an admin POSTs to `/run` with that path
- **THEN** the dispatcher SHALL select dosbox-x
- **AND** the host SHALL spawn a container using
  `dosbox_x.session_config()`
- **AND** the response SHALL be `200 {session_id, host, port}`
- **AND** an audit-log entry SHALL be written with
  `outcome=dispatched`, `selected_engine=dosbox-x`.

#### Scenario: ELF file refused with 415

- **GIVEN** no engine claims the `elf` magic family in v1
- **WHEN** an admin POSTs to `/run` with a path whose detected
  magic family is `elf`
- **THEN** the dispatcher SHALL return `415 Unsupported Media Type`
  with the detected family in the response body
- **AND** an audit-log entry SHALL be written with
  `outcome=refused`, `selected_engine=null`, `reason="no engine"`.

#### Scenario: Non-admin blocked at API

- **GIVEN** a non-admin user
- **WHEN** they POST to `/run`
- **THEN** the dispatcher SHALL return `403 Forbidden`
- **AND** an audit-log entry SHALL be written with
  `outcome=refused`, `reason="not admin"`.

### Requirement: Self-test reports real per-check status

The `/selftest` endpoint SHALL execute four named checks
(`host-health`, `engines-registered`, `deploy-daemon-spawn`,
`audit-log-write`) and return their actual results in the JSON
shape locked by `init-mvp-runtime`. The schema (field names,
order of checks) MUST NOT change.

#### Scenario: All four checks pass on a healthy install

- **GIVEN** a healthy host, a registered enabled engine, a
  reachable deploy daemon, and a writable audit log
- **WHEN** an admin POSTs to `/selftest`
- **THEN** every check SHALL return `status: "ok"`
- **AND** the `overall` field SHALL be `"ok"`
- **AND** the order of checks in the response SHALL be exactly
  `[host-health, engines-registered, deploy-daemon-spawn,
   audit-log-write]`.

#### Scenario: Failing check reports actual error

- **GIVEN** the deploy daemon is unreachable
- **WHEN** an admin POSTs to `/selftest`
- **THEN** the `deploy-daemon-spawn` check SHALL return
  `status: "fail"` with `message` containing the actual error
  surface (HTTP status, hostname, or transport error)
- **AND** the `overall` field SHALL be `"fail"`
- **AND** the response SHALL NOT fall back to vague text like
  "something went wrong".

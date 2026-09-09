# Sandbox — spec deltas

These requirements described a sibling container the host cannot spawn.
What replaces them is weaker in exactly one way, and this delta says so
plainly rather than restating the old promise in new words.

## REMOVED Requirements

### Requirement: Resource limits enforced at container level

**Reason**: there is no per-session container to apply cgroup limits to.
Replaced by *Session resources are bounded by what the runtime offers*,
which states what is actually enforced and what is not.

### Requirement: Read-only root filesystem

**Reason**: the session runs in the app's own container, whose root
filesystem the app itself needs. Replaced by *A session writes only
inside its own directory*, which bounds the writable surface where it
can still be bounded.

## ADDED Requirements

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

# Sandbox — spec deltas

## ADDED Requirements

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

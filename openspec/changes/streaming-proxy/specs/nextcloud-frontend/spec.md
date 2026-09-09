# Nextcloud frontend — spec deltas

## ADDED Requirements

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

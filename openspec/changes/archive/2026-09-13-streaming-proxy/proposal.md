# Change: streaming-proxy

## Why

`wire-dosbox-engine` got the Run flow working: an admin right-clicks a
binary in Files, the host starts a session, and DOSBox-X runs the
program with KasmVNC serving its screen on the session's port. Measured
live on NC 32.0.14 + AppAPI 5.x + HaRP v0.4.0 — the emulator runs, the
port answers.

What nobody can do is *see* it. The session page says "the session is
running" and nothing more, because the only door into the app is the
AppAPI proxy and nothing routes KasmVNC through it yet. A DOS program
you cannot look at is not a feature.

Two smaller things wait on the same plumbing:

- **Idle termination.** The `engines` spec says idle-based termination
  applies "once the streaming layer reports per-session activity". The
  host cannot see websocket traffic that does not pass through it. Route
  the stream through the shim and the signal exists, so a forgotten
  session stops costing CPU.
- **Per-session credentials.** KasmVNC currently answers 401 with a
  password baked into the image at build time (`demo`). That is a
  demo-mode shortcut the security model already flags; a session that is
  reachable from a browser needs a credential that belongs to that
  session and dies with it.

## What changes

- **The shim relays the stream.** `GET /sessions/{id}/stream/…` (and its
  websocket upgrade) proxies to the session's KasmVNC port on
  `127.0.0.1`, with the caller's admin identity checked against the
  session's owner before a single byte is forwarded.
- **The session page shows the picture.** `IframeHost.vue` stops being a
  placeholder and hosts the KasmVNC client; `SessionStatus.vue` mounts
  it instead of the "no stream yet" note.
- **Per-session KasmVNC credentials**, issued when the session starts,
  written to a per-session password file, gone when it ends.
- **Idle timeout** driven by the relay's own traffic: no bytes either way
  for the configured window (default 900 s) terminates the session, and
  the `engines` spec's conditional requirement becomes unconditional.

## The awkward part, said out loud

`wire-dosbox-engine`'s design carries a "boring valkuil": *don't roll a
custom websocket proxy — KasmVNC's client and the AppAPI proxy network
are the planned path.* This change rolls one anyway, and the reason is
the topology it inherited rather than a change of taste: AppAPI gives an
ExApp exactly one port, and the sessions live behind it on ports of
their own. Nothing else can bridge that. What the warning still buys us
is scope: relay bytes, do not reimplement the client, do not touch the
RFB protocol, and keep KasmVNC's own web client as the thing the iframe
loads.

An unmeasured assumption sits under all of it: that a websocket survives
the whole chain (browser → Nextcloud → AppAPI proxy → HaRP → the FRP
tunnel → the shim). Nobody has tested that. The first task measures it,
before any UI is built on top.

## Impact

- `host/src/ash_nazg/` gains the relay; `spawners.py` gains per-session
  credentials and an activity clock.
- `frontend/src/IframeHost.vue` + `SessionStatus.vue`.
- `appinfo/info.xml` gains the stream route.
- The level-3 verifier gains a browser step: the existing suites are
  curl-shaped, and a stream is not.

## Wat hier NIET in zit

- Audio, clipboard, file transfer through KasmVNC. Out of scope until
  someone asks for them, and each has its own leak surface.
- Multi-user viewing of one session.
- Replacing KasmVNC. It is the boring choice and it works.

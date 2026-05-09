# wire-dosbox-engine

## Why

`init-mvp-runtime` produced a complete scaffolding: the manifest
registers, the host's `/health` and `/heartbeat` respond, the admin
page renders, the Files action is registered, the self-test
endpoint returns the canonical four-check shape with all values set
to `skipped`. Nothing actually runs a binary.

This change fills the gap. After it lands, an admin can upload
`keen1.exe` to Files, right-click → *Run with Ash Nazg*, and a
DOSBox-X engine container spawns, mounts the user's Files via
WebDAV, and starts the binary. The session is observable but not
yet streamed in-browser — KasmVNC iframe plumbing is the next
change (`streaming-proxy`).

## What Changes

**Scope: dispatcher + engine lifecycle + AppAPI handshake + real
self-test + working engine entrypoint.**

- **Host dispatcher.** `host/src/ash_nazg/dispatch.py` (new)
  detects file format from magic bytes (per `detection` spec),
  selects the first-registered engine whose `can_handle()` returns
  True, asks the engine for its `SessionConfig`, and spawns the
  container via the AppAPI deploy daemon. Replaces the `/run` 501
  stub.
- **Engine registry.** `host/src/ash_nazg/engines/registry.py` (new)
  iterates over the `ash_nazg.engines` Python entrypoint group,
  filters out engines disabled by admin settings, and exposes the
  ordered list to the dispatcher.
- **dosbox-x engine plugin.** `host/src/ash_nazg/engines/dosbox_x.py`
  (new) is the first concrete `Engine` Protocol implementation —
  `can_handle()` returns True for `pe32` / `mz-dos` / `pe32-plus`,
  `session_config()` returns the canonical SessionConfig from the
  `engines` capability spec.
- **AppAPI registration.** `appapi.register()` becomes real
  (currently `NotImplementedError`).
- **Real self-test.** `selftest.py` swaps each `"skipped"` value
  for an actual check, keeping the JSON shape unchanged.
- **Engine entrypoint.** `engines/dosbox-x/entrypoint.sh` replaces
  its stub: mounts `/mnt/files` via davfs2 using the host-injected
  token, then `exec dosbox-x` with the file path resolved under
  the mount. (KasmVNC server is launched here too, but the proxy
  surface that exposes it to the browser is `streaming-proxy`.)
- **Frontend.** `files-action.ts`'s `exec` calls `POST /run` and
  navigates to a session page that shows a "session running"
  status — without the iframe stream (still `streaming-proxy`).

## Impact

**Touched code:**
- `host/src/ash_nazg/{dispatch,engines/registry,engines/dosbox_x}.py`
  (new), `host/src/ash_nazg/{main,appapi,selftest}.py` (modified).
- `host/tests/` gains dispatch + registry + dosbox-x unit tests
  and a host-only integration test that mocks the deploy daemon.
- `engines/dosbox-x/entrypoint.sh` (rewrite from stub).
- `frontend/src/files-action.ts` (`exec` wired) and a new
  `frontend/src/SessionStatus.vue` for the no-streaming session
  view.
- `openspec/changes/wire-dosbox-engine/specs/dispatch/spec.md` (new),
  plus delta entries for `engines` and `sandbox` if needed.

**Out of scope (own future change):**
- KasmVNC iframe + websocket proxy → `streaming-proxy`.
- Per-engine admin-settings persistence → `admin-settings-ui`.
- App Store submission → `appstore-v1-submission`.

**Boring valkuil:**
Don't roll a custom websocket proxy "to keep streaming-proxy
small". KasmVNC's existing client + the AppAPI proxy network are
the planned path; bypassing either creates throwaway code.

> **Status: DRAFT.** This proposal is the bridge from
> `init-mvp-runtime`'s scaffold; the full set of spec deltas and
> task breakdown is fleshed out at the start of the
> `wire-dosbox-engine` implementation session.

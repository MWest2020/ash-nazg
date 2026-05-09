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

## Acceptance criteria

The change is "done" when **all** of these hold against the level-3
verifier (`scripts/verify-against-nextcloud.sh`) running the migrated
test target (NC 32 + AppAPI 5.x; see below):

- The host shim advertises its listen port to AppAPI via the
  official AppAPI 5.x registration handshake, AND
- `oc_ex_apps.port` for `ash_nazg` matches what the host actually
  listens on **without** any direct DB UPDATE in the bootstrap.
  The `init-mvp-runtime` scaffold's
  `bootstrap-nextcloud.sh` patches `port=8080` via SQL as a
  workaround for AppAPI 4.0.6 manual-install behaviour; this change
  retires that. Re-running the bootstrap after the wiring lands
  must produce a working install with the SQL block deleted.
- `POST /run` against the host shim spawns a dosbox-x engine
  container, returns `200 {session_id, host, port}`, and the
  spawned container is observable via `docker ps`.
- `POST /selftest` returns `status: "ok"` for all four canonical
  check IDs on a healthy install (and per-check "fail" with an
  actual error message on a broken install — never vague text).
- The Files action's `exec` calls `POST /run` and navigates to a
  session-status page on success; toasts the actual error on
  failure.
- The level-3 verifier script asserts every bullet above
  programmatically — no "verified by review" entries.

## Test target migration (NC 30 → NC 32, AppAPI 4 → 5)

The `init-mvp-runtime` level-3 verifier ran against
`nextcloud:30-apache`, which bundles AppAPI 4.0.6. Two reasons to
migrate this change's verifier to `nextcloud:32-apache` with
AppAPI 5.x:

1. **NC 30's support window is closing.** NC 30 was released
   2024-09; by the time this change ships, NC 32 will be the
   actively-supported release and NC 30 will be on or near
   end-of-maintenance. Building the demo on a release that's
   about to drop out of maintenance is the wrong direction.
2. **AppAPI 5.x has the manual-install flow we actually need.**
   The 4.0.6 manual-install path auto-allocates an ExApp port
   (~23000) on register and provides no native way to override
   it — we ended up DB-poking `oc_ex_apps.port`. AppAPI 5.x ships
   a real registration handshake where the ExApp advertises its
   listen port (and routes, scopes, etc.) back to AppAPI. That's
   the canonical solution; building against 4.0.6 would mean
   designing around a workaround we'd then have to remove for 5.x
   anyway.

What changes operationally:

- `scripts/local-nextcloud-stack.yml` — bump `nextcloud:30-apache`
  to `nextcloud:32-apache`. Verify postgres + valkey image tags
  still resolve cleanly against the NC 32 PHP version.
- `scripts/bootstrap-nextcloud.sh` — confirm the AppAPI install
  path still works (`occ app:install app_api`); update the
  daemon-register call if AppAPI 5.x has changed the positional
  arg set; **delete** the `oc_ex_apps.port` SQL UPDATE.
- `scripts/verify-against-nextcloud.sh` — re-run against the new
  target; assertions stay the same, but
  the AppAPI proxy URL test
  (`/index.php/apps/app_api/proxy/ash_nazg/health`) flips from "404
  by design" to "200" because route registration now happens via
  the handshake.
- `docs/installation.md` — bump the documented minimum to NC 32 +
  AppAPI 5.x.

NC 30 + AppAPI 4 stays mentioned in `CHANGELOG.md` as the version
the scaffold was first verified against — historical record, not a
support claim.

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

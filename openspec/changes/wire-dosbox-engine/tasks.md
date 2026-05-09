# Tasks — wire-dosbox-engine

> **Status: DRAFT.** Skeleton. Refine into concrete sub-tasks at
> the start of the implementation session via `/opsx:propose`-style
> drill-down.

## 1. Engine registry

- [ ] 1.1 `host/src/ash_nazg/engines/registry.py` discovers engines
        via the `ash_nazg.engines` Python entrypoint group.
- [ ] 1.2 Broken engines (missing attrs, raises on load) are logged
        and skipped without taking the host down.
- [ ] 1.3 Admin-disabled engines are excluded from the dispatch
        list. New engines default to disabled.

## 2. dosbox-x engine plugin

- [ ] 2.1 `host/src/ash_nazg/engines/dosbox_x.py` implements the
        `Engine` Protocol. `can_handle()` returns True for `pe32`,
        `pe32-plus`, `mz-dos`.
- [ ] 2.2 `session_config()` returns the canonical SessionConfig
        from `engines/spec.md` (1 CPU, 1024 MB, 900 s idle, port
        6901, `/mnt/files`).
- [ ] 2.3 Registered as a `[project.entry-points."ash_nazg.engines"]`
        in `host/pyproject.toml`.

## 3. Dispatcher

- [ ] 3.1 `host/src/ash_nazg/dispatch.py` reads the file's first
        ≤512 bytes via WebDAV range request, classifies, and
        selects an engine.
- [ ] 3.2 `/run` endpoint replaces the 501 stub; returns
        `{session_id, host, port}` on success, `415` for unhandled
        formats, `400` for unrecognised, `403` for non-admin.
- [ ] 3.3 Per-dispatch audit-log entry per `detection` and
        `sandbox` specs.

## 4. AppAPI registration (AppAPI 5.x)

- [ ] 4.1 `appapi.register()` becomes real (replaces
        `NotImplementedError`). Builds and POSTs the canonical
        payload to `{NEXTCLOUD_URL}/index.php/apps/app_api/api/v1/exapp/register`
        per `design.md` § *AppAPI registration handshake*.
- [ ] 4.2 Wired into the FastAPI `lifespan` hook so it runs at
        startup, before the server starts accepting `/run`.
- [ ] 4.3 Payload **MUST** include the host shim's actual listen
        port (`APP_PORT` env), so AppAPI stores the correct value in
        `oc_ex_apps.port` directly — no scaffold-era SQL UPDATE.
- [ ] 4.4 Payload **MUST** declare every proxy route the ExApp
        wants to expose (`/health`, `/admin/settings`,
        `/selftest`, `/run`, plus the static-bundle paths).
        Without this, the AppAPI proxy 404s; with it, NC users
        reach the admin page through the canonical
        `/index.php/apps/app_api/proxy/ash_nazg/...` URL.
- [ ] 4.5 Exponential-backoff retry up to 5 minutes; non-zero exit
        on persistent failure. Distinguish "AppAPI unreachable"
        from "AppAPI rejected manifest" in the error log.

## 4b. Retire the scaffold port-poke (acceptance gate)

- [ ] 4b.1 Delete the `oc_ex_apps.port` SQL UPDATE block from
        `scripts/bootstrap-nextcloud.sh`. Re-run
        `scripts/verify-against-nextcloud.sh` against the migrated
        target (NC 32 + AppAPI 5.x). All assertions still pass —
        proves the handshake set the port, not us.
- [ ] 4b.2 Remove the "by design 404" caveat for the proxy URL
        from `docs/testing.md`. Add a positive assertion in
        `verify-against-nextcloud.sh` that
        `GET /index.php/apps/app_api/proxy/ash_nazg/health`
        through NC's basic-auth returns the canonical
        `{"status":"ok","app":"ash_nazg",…}` body.

## 4c. Test-target migration (NC 30 → NC 32)

- [ ] 4c.1 `scripts/local-nextcloud-stack.yml` — bump
        `nextcloud:30-apache` → `nextcloud:32-apache`. Verify
        postgres + valkey image tags still resolve cleanly against
        NC 32's PHP version.
- [ ] 4c.2 If AppAPI 5.x has shifted any positional args on
        `app_api:daemon:register` or `app_api:app:register`, update
        `scripts/bootstrap-nextcloud.sh` to match. Document the
        diff inline.
- [ ] 4c.3 `docs/installation.md` — bump the documented minimum
        Nextcloud version to 32 and AppAPI to 5.x. NC 30 + AppAPI
        4.0.6 stays only in `CHANGELOG.md` as the historical
        first-verified target.

## 5. Engine container entrypoint

- [ ] 5.1 `engines/dosbox-x/entrypoint.sh` mounts `/mnt/files` via
        davfs2 using `NEXTCLOUD_URL` + `APP_TOKEN` injected by the
        host.
- [ ] 5.2 Launches `kasmvncserver` on port 6901 (the proxy that
        exposes it to the browser is `streaming-proxy`).
- [ ] 5.3 `exec dosbox-x <FILE_PATH>` with the path resolved under
        `/mnt/files`.

## 6. Frontend wiring

- [ ] 6.1 `frontend/src/files-action.ts` `exec` calls `POST /run`
        and navigates to the session status page on success;
        toasts on error (using the actual error from the host's
        response, never "something went wrong").
- [ ] 6.2 `frontend/src/SessionStatus.vue` shows session id, engine
        name, and a "session running" status. No iframe stream
        (that's `streaming-proxy`).

## 7. Self-test — replace stubs with real checks

- [ ] 7.1 `host-health`: in-container `/health` probe.
- [ ] 7.2 `engines-registered`: ≥1 enabled engine.
- [ ] 7.3 `deploy-daemon-spawn`: spawn + tear down a busybox
        sidecar within 30 s.
- [ ] 7.4 `audit-log-write`: write `ash_nazg.selftest` and assert
        2xx from the AppAPI audit-log API.

## 8. Tests

- [ ] 8.1 Unit tests for `dispatch.detect()` covering every magic
        family from the `detection` spec.
- [ ] 8.2 Unit tests for `registry` covering load failures,
        admin-disable, ordering.
- [ ] 8.3 Host-only integration test that mocks the deploy daemon
        and asserts a successful spawn pipeline end-to-end.

## 9. Hand-off

- [ ] 9.1 Open `streaming-proxy` change: KasmVNC iframe + websocket
        proxy through AppAPI's HaRP network.
- [ ] 9.2 Archive `wire-dosbox-engine` once tasks 1–8 are green
        and a manual run on a real Nextcloud has produced
        DOSBox-X output (no streaming yet — `docker exec` into the
        engine container to verify).

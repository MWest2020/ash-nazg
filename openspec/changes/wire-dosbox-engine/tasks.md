# Tasks — wire-dosbox-engine

> **Status: DRAFT.** Skeleton. Refine into concrete sub-tasks at
> the start of the implementation session via `/opsx:propose`-style
> drill-down.
>
> **Architectural decision (locked in):** docker-install via HaRP
> for **both** production and level-3. See `design.md` §
> *Decision: (c) — docker-install via HaRP*. Manual-install with a
> SQL workaround was the scaffolding compromise; this change ends
> it. Tasks below are ordered to validate the verifier and image
> distribution path BEFORE writing any engine wiring on top.

## 1. HaRP-based level-3 verifier rewrite

The scaffold's `scripts/local-nextcloud-stack.yml` runs the host
container directly under compose with manual-install + a SQL port
patch. That model is retired in this change.

- [ ] 1.1 Add an `appapi-harp` service to
        `scripts/local-nextcloud-stack.yml` — image
        `ghcr.io/nextcloud/nextcloud-appapi-harp` (verify exact
        repo path against AppAPI 5.x docs at implementation time),
        with the rootless podman socket mounted at
        `/var/run/docker.sock`. Wire it onto the same network as
        Nextcloud.
- [ ] 1.2 **Remove** the `ash-nazg-host` service from the compose
        file. HaRP spawns it on demand at `app_api:app:register`
        time; it must NOT be co-started by compose.
- [ ] 1.3 Rewrite `scripts/bootstrap-nextcloud.sh`:
    - Register the HaRP daemon with `docker-install` deploy id
      (replacing the manual-install daemon).
    - Register the ExApp via `app_api:app:register ash_nazg
      <harp-daemon> --info-xml=/tmp/info.xml --wait-finish`.
    - **Delete** the `UPDATE oc_ex_apps SET port = 8080` SQL
      block — HaRP allocates the port and spawns the container
      with `APP_PORT=<that>` directly, so no patching is needed.
    - Delete the docker-cp of `info.xml` if AppAPI 5.x can read
      it from a different path; otherwise keep that step but
      document why.
- [ ] 1.4 Update `scripts/verify-against-nextcloud.sh` assertions:
    - Keep: `/health` returns canonical body, `/selftest` returns
      4-check skipped JSON, `/admin/settings` shell renders.
    - **New positive assertion**: `GET /index.php/apps/app_api/proxy/ash_nazg/health`
      through NC's basic-auth returns the canonical
      `{"status":"ok","app":"ash_nazg",…}` body. This replaces
      the "404-by-design" caveat from `docs/testing.md`.
    - **New positive assertion**: container spawned by HaRP shows
      up in `docker ps` with the expected name pattern.
- [ ] 1.5 Update `docs/testing.md`:
    - Remove the "404 is by design" wording for the proxy URL.
    - Document the new HaRP dependency (rootless podman socket,
      or rootful docker socket; both supported).
    - Document the level-3 startup time impact (~3-5 min more
      due to HaRP + first GHCR pull).

## 2. GHCR image-pull validation

Validates the App Store distribution path *before* writing engine
wiring on top. If GHCR pulls fail in HaRP, no amount of dispatcher
code helps.

- [ ] 2.1 Push host + engine images to GHCR under a `wire-dosbox-engine`
        development tag (e.g. `0.1.0-wire-dev`) — this is the first
        time `build-host.yml` and `build-engine-dosbox.yml` actually
        push from a non-tag context. Use a temp branch + the
        existing workflows' `type=ref,event=branch` tag pattern.
- [ ] 2.2 Update `appinfo/info.xml` `<image-tag>` to the same
        `0.1.0-wire-dev` value (still no `latest`; the
        `verify-info-xml.sh` allowlist still passes).
- [ ] 2.3 Re-run the level-3 verifier against the now-rewritten
        compose stack. HaRP pulls from `ghcr.io/...` and spawns a
        fresh container — no `localhost/ash-nazg-host` dependency.
- [ ] 2.4 If the pull fails on auth, document the credential
        requirement (HaRP needs a GHCR token for private repos;
        public repos need none). For our public repo, expect no
        auth needed.
- [ ] 2.5 The `verify-images-published.yml` workflow (already
        added in `init-mvp-runtime`) gates tag-push releases on
        `docker manifest inspect` of both images. Verify it still
        passes for the dev tag, then keep it as the App Store
        submission gate it was always meant to be.

## 3. Engine registry

- [ ] 3.1 `host/src/ash_nazg/engines/registry.py` discovers engines
        via the `ash_nazg.engines` Python entrypoint group.
- [ ] 3.2 Broken engines (missing attrs, raises on load) are logged
        and skipped without taking the host down.
- [ ] 3.3 Admin-disabled engines are excluded from the dispatch
        list. New engines default to disabled.

## 4. dosbox-x engine plugin

- [ ] 4.1 `host/src/ash_nazg/engines/dosbox_x.py` implements the
        `Engine` Protocol. `can_handle()` returns True for `pe32`,
        `pe32-plus`, `mz-dos`.
- [ ] 4.2 `session_config()` returns the canonical SessionConfig
        from `engines/spec.md` (1 CPU, 1024 MB, 900 s idle, port
        6901, `/mnt/files`).
- [ ] 4.3 Registered as a `[project.entry-points."ash_nazg.engines"]`
        in `host/pyproject.toml`.

## 5. Dispatcher

- [ ] 5.1 `host/src/ash_nazg/dispatch.py` reads the file's first
        ≤512 bytes via WebDAV range request, classifies, and
        selects an engine.
- [ ] 5.2 `/run` endpoint replaces the 501 stub; returns
        `{session_id, host, port}` on success, `415` for unhandled
        formats, `400` for unrecognised, `403` for non-admin.
- [ ] 5.3 Per-dispatch audit-log entry per `detection` and
        `sandbox` specs.

## 6. AppAPI registration handshake (HaRP-spawned env consumption)

In docker-install via HaRP, AppAPI sets `APP_HOST`, `APP_PORT`,
`APP_SECRET`, `APP_VERSION`, `APP_ID`, `NEXTCLOUD_URL` as env
vars on the spawned container. The host shim **accepts** these,
not chooses them.

- [ ] 6.1 `appapi.register()` becomes real (replaces
        `NotImplementedError`). Reads the env vars HaRP set,
        binds uvicorn to `APP_PORT`, and POSTs the **route
        registration** to AppAPI (the port is already known to
        AppAPI; only the routes still need explicit declaration).
- [ ] 6.2 Wired into the FastAPI `lifespan` hook so it runs at
        startup, before the server starts accepting `/run`.
- [ ] 6.3 Routes payload includes every proxy path the ExApp
        wants exposed: `/health`, `/admin/settings`, `/selftest`,
        `/run`, plus the static-bundle paths under `/static/...`.
        Without this, the AppAPI proxy 404s; with it, NC users
        reach the admin page through
        `/index.php/apps/app_api/proxy/ash_nazg/...`.
- [ ] 6.4 Exponential-backoff retry up to 5 minutes on
        registration failure; non-zero exit on persistent
        failure. Distinguish "AppAPI unreachable" from "AppAPI
        rejected payload" in the error log.

## 7. Engine container entrypoint

- [ ] 7.1 `engines/dosbox-x/entrypoint.sh` mounts `/mnt/files` via
        davfs2 using `NEXTCLOUD_URL` + `APP_TOKEN` injected by the
        host.
- [ ] 7.2 Launches `kasmvncserver` on port 6901 (the proxy that
        exposes it to the browser is `streaming-proxy`).
- [ ] 7.3 `exec dosbox-x <FILE_PATH>` with the path resolved under
        `/mnt/files`.

## 8. Frontend wiring

- [ ] 8.1 `frontend/src/files-action.ts` `exec` calls `POST /run`
        and navigates to the session status page on success;
        toasts on error (using the actual error from the host's
        response, never "something went wrong").
- [ ] 8.2 `frontend/src/SessionStatus.vue` shows session id, engine
        name, and a "session running" status. No iframe stream
        (that's `streaming-proxy`).

## 9. Self-test — replace stubs with real checks

- [ ] 9.1 `host-health`: in-container `/health` probe.
- [ ] 9.2 `engines-registered`: ≥1 enabled engine.
- [ ] 9.3 `deploy-daemon-spawn`: spawn + tear down a busybox
        sidecar via HaRP within 30 s. Rewrites the original
        AppAPI-4 manual-install version of this check.
- [ ] 9.4 `audit-log-write`: write `ash_nazg.selftest` and assert
        2xx from the AppAPI audit-log API.

## 10. Tests

- [ ] 10.1 Unit tests for `dispatch.detect()` covering every
        magic family from the `detection` spec.
- [ ] 10.2 Unit tests for `registry` covering load failures,
        admin-disable, ordering.
- [ ] 10.3 Host-only integration test that mocks AppAPI's
        spawn-time env injection and asserts the host shim binds
        to `APP_PORT` and registers its routes.

## 11. Docs touch-ups (small but non-trivial)

- [ ] 11.1 `docs/installation.md` — bump documented minimum to
        NC 32 + AppAPI 5.x. NC 30 + AppAPI 4.0.6 stays in
        `CHANGELOG.md` as the historical first-verified target,
        not a support claim.
- [ ] 11.2 `docs/testing.md` — remove the "404 is by design"
        wording for the proxy URL (handled in §1.5 above as part
        of the verifier rewrite, but worth the explicit checkbox).

## 12. Hand-off

- [ ] 12.1 Open `streaming-proxy` change: KasmVNC iframe +
        websocket proxy through AppAPI's HaRP network.
- [ ] 12.2 Archive `wire-dosbox-engine` once §1–§10 are green and
        a manual run produces DOSBox-X output (no streaming yet
        — `docker exec` into the engine container to verify).

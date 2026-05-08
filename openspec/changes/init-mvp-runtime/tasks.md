# Tasks — init-mvp-runtime

> Scaffolding only. After this change is archived, the repo has empty
> houses for every component. Subsequent changes (`wire-dosbox-engine`,
> `streaming-proxy`, etc.) put logic inside them.

## 0. Preflight

- [ ] 0.1 Verify AppAPI version compatibility: confirm Nextcloud 30+ is the
        target floor and that AppAPI 5.x is GA. Run on a test instance:
        `occ app:list | grep app_api` and document the version in
        `docs/compatibility.md`.
- [ ] 0.2 Confirm HaRP availability on target Nextcloud installs.
        Document in `docs/installation.md` that DSP is NOT supported.
- [ ] 0.3 Reserve the `ash-nazg` app ID by drafting (not submitting) the
        App Store listing. Verify no collision.

## 1. Repo skeleton

- [ ] 1.1 Initialize git repo, push to `github.com/MWest2020/ash-nazg`
        (or chosen org). Default branch `main`. Add branch protection
        for direct pushes.
- [ ] 1.2 Create `README.md` with: one-paragraph description, demo
        screenshot placeholder, status badge ("alpha — not for production"),
        Tolkien-disclaimer footer, AGPL-3.0 license note.
- [ ] 1.3 Create `LICENSE` (AGPL-3.0). Add `THIRD_PARTY_NOTICES.md`
        listing DOSBox-X (GPL-2.0), KasmVNC (GPL-3.0), davfs2 (GPL-2.0),
        FastAPI (MIT), Vue 3 (MIT), @nextcloud/vue (AGPL-3.0).
- [ ] 1.4 Create `SECURITY.md` describing reporting policy
        (security@ email, 90-day disclosure default).
- [ ] 1.5 Create `CONTRIBUTING.md` describing OpenSpec workflow:
        every change goes through `/opsx:propose`, no direct
        implementation PRs without an open change.
- [ ] 1.6 Create `.gitignore` covering Python, Node, Docker, IDE files,
        `.env`, `*.local`.
- [ ] 1.7 Create `.editorconfig` aligned with Nextcloud conventions
        (2-space indent for JS/Vue, 4-space for Python, LF line endings).

## 2. OpenSpec scaffolding

- [ ] 2.1 `openspec/config.yaml` exists at repo root (this change creates it).
- [ ] 2.2 Empty `openspec/specs/` directory committed with `.gitkeep`.
        Specs live here once changes archive.
- [ ] 2.3 This change folder is in place: `openspec/changes/init-mvp-runtime/`.
- [ ] 2.4 Run `openspec validate init-mvp-runtime` and resolve any warnings.

## 3. Host container scaffold

- [ ] 3.1 `host/` directory with `pyproject.toml` (Python 3.12, FastAPI,
        uvicorn, httpx, pydantic v2). Use `uv` for dependency management
        (per project preference: never raw pip).
- [ ] 3.2 `host/src/ash_nazg/main.py` with FastAPI app, `/health`,
        `/heartbeat` endpoints (the AppAPI-required ones), and a stub
        `/run` endpoint that returns 501 Not Implemented.
- [ ] 3.3 `host/src/ash_nazg/appapi.py` with the registration handshake
        skeleton, scoped per AppAPI 5.x conventions.
- [ ] 3.4 `host/src/ash_nazg/engines/__init__.py` declaring the `Engine`
        Protocol (per design.md). No concrete engines yet.
- [ ] 3.5 `host/Dockerfile` building a slim image. Multi-stage; final
        image runs as non-root, uvicorn entrypoint.
- [ ] 3.6 `host/tests/test_health.py` with a single passing test against
        `/health`. Uses pytest.

## 4. Engine container scaffold

- [ ] 4.1 `engines/dosbox-x/Dockerfile` based on `debian:12-slim`,
        installs `dosbox-x`, `kasmvnc`, `davfs2`, `tini`. No config wired
        yet — image just has the binaries available.
- [ ] 4.2 `engines/dosbox-x/entrypoint.sh` is a stub that prints
        "ash-nazg dosbox-x engine container — wiring TBD" and exits 0.
        The wiring change replaces this.
- [ ] 4.3 `engines/dosbox-x/README.md` describes the image's role and
        intended interface contract (env vars expected, ports exposed,
        mount points).

## 5. Frontend scaffold

- [ ] 5.1 `frontend/` directory bootstrapped with Vite + Vue 3 + TypeScript.
        Use Nextcloud's `@nextcloud/vue` and `@nextcloud/files` libraries.
- [ ] 5.2 `frontend/src/files-action.ts` registers a placeholder
        right-click action on every file, displaying a toast "Ash Nazg
        not yet wired" when clicked. Wiring is the next change.
- [ ] 5.3 `frontend/src/IframeHost.vue` is an empty Vue component that
        renders a placeholder div where the KasmVNC iframe will go.
- [ ] 5.4 `frontend/package.json` build script outputs to
        `host/static/` so the host container serves the frontend bundle.

## 6. Nextcloud app metadata

- [ ] 6.1 `appinfo/info.xml` declaring: id `ash-nazg`, name "Ash Nazg",
        summary one-line, description multi-line, category `tools`,
        AppAPI dependency, `<external-app><docker-install>` block
        pointing at `ghcr.io/mwest2020/ash-nazg-host:placeholder`.
        Required scopes: FILES, AUDIT_LOGS, NOTIFICATIONS.
- [ ] 6.2 `appinfo/screenshots/` with placeholder PNGs (real
        screenshots come after demo works).

## 7. CI plumbing

- [ ] 7.1 `.github/workflows/build-host.yml`: on push to main and on tag,
        builds `ash-nazg-host` multi-arch (amd64+arm64), pushes to GHCR.
        Uses `docker/build-push-action`.
- [ ] 7.2 `.github/workflows/build-engine-dosbox.yml`: same for the
        engine image.
- [ ] 7.3 `.github/workflows/test.yml`: runs `pytest` on the host code,
        `npm run lint && npm run build` on the frontend. Required for PR
        merges.
- [ ] 7.4 `.github/workflows/openspec-validate.yml`: runs `openspec validate`
        against any change folder touched in a PR.

## 8. Docs scaffolding

- [ ] 8.1 `docs/installation.md` — placeholder explaining HaRP requirement,
        admin install steps (App Store install, enable in admin UI).
        Marked "draft — needs end-to-end test".
- [ ] 8.2 `docs/user-guide.md` — placeholder for "how to upload and run
        a binary". Marked "draft".
- [ ] 8.3 `docs/security-model.md` — written now (not placeholder),
        capturing the design.md security posture for non-OpenSpec
        readers.
- [ ] 8.4 `docs/bring-your-own-content.md` — written now, explaining
        the legal boundary: users provide their own Win 3.11 install
        floppies, their own ROMs if a future engine adds emulator
        support, their own DOS games. Project ships zero non-open
        content.

## 9. Validation

- [ ] 9.1 `docker build` succeeds for both host and dosbox-x engine
        images locally.
- [ ] 9.2 `openspec validate init-mvp-runtime` passes with no warnings.
- [ ] 9.3 The placeholder host container, when run with `docker run`,
        responds 200 on `/health`.
- [ ] 9.4 Frontend builds without errors via `npm run build`.
- [ ] 9.5 `info.xml` validates against the Nextcloud app schema
        (`occ app:check ash-nazg` on a dev instance, or the schema
        validator from `nextcloud/appstore`).

## 10. Hand-off to next change

- [ ] 10.1 Open the next change with `/opsx:propose wire-dosbox-engine`.
        Its scope: implement the dispatcher logic, the engine
        spawn/lifecycle, and the file action so a user can actually
        click Run and see DOSBox-X start. Streaming and WebDAV mount
        are separate subsequent changes.
- [ ] 10.2 Archive this change with `/opsx:archive init-mvp-runtime`.
        Confirm specs merge into `openspec/specs/`.

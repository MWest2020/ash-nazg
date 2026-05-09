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
- [x] 1.2 Create `README.md` with: one-paragraph description, demo
        screenshot placeholder, status badge ("alpha — not for production"),
        Tolkien-disclaimer footer, AGPL-3.0 license note.
- [x] 1.3 Create `LICENSE` (AGPL-3.0). Add `THIRD_PARTY_NOTICES.md`
        listing DOSBox-X (GPL-2.0), KasmVNC (GPL-3.0), davfs2 (GPL-2.0),
        FastAPI (MIT), Vue 3 (MIT), @nextcloud/vue (AGPL-3.0).
- [x] 1.4 Create `SECURITY.md` describing reporting policy
        (security@ email, 90-day disclosure default).
- [x] 1.5 Create `CONTRIBUTING.md` describing OpenSpec workflow:
        every change goes through `/opsx:propose`, no direct
        implementation PRs without an open change.
- [x] 1.6 Create `.gitignore` covering Python, Node, Docker, IDE files,
        `.env`, `*.local`.
- [x] 1.7 Create `.editorconfig` aligned with Nextcloud conventions
        (2-space indent for JS/Vue, 4-space for Python, LF line endings).

## 2. OpenSpec scaffolding

- [x] 2.1 `openspec/config.yaml` exists at repo root (this change creates it).
- [x] 2.2 Empty `openspec/specs/` directory committed with `.gitkeep`.
        Specs live here once changes archive.
- [x] 2.3 This change folder is in place: `openspec/changes/init-mvp-runtime/`.
- [x] 2.4 Run `openspec validate init-mvp-runtime` and resolve any warnings.

## 3. Host container scaffold

- [x] 3.1 `host/` directory with `pyproject.toml` (Python 3.12, FastAPI,
        uvicorn, httpx, pydantic v2). Use `uv` for dependency management
        (per project preference: never raw pip).
- [x] 3.2 `host/src/ash_nazg/main.py` with FastAPI app, `/health`,
        `/heartbeat` endpoints (the AppAPI-required ones), and a stub
        `/run` endpoint that returns 501 Not Implemented.
- [x] 3.3 `host/src/ash_nazg/appapi.py` with the registration handshake
        skeleton, scoped per AppAPI 5.x conventions.
- [x] 3.4 `host/src/ash_nazg/engines/__init__.py` declaring the `Engine`
        Protocol (per design.md). No concrete engines yet.
- [x] 3.5 `host/Dockerfile` building a slim image. Multi-stage; final
        image runs as non-root, uvicorn entrypoint.
- [x] 3.6 `host/tests/test_health.py` with a single passing test against
        `/health`. Uses pytest.

## 4. Engine container scaffold

- [x] 4.1 `engines/dosbox-x/Dockerfile` based on `debian:12-slim`,
        installs `dosbox-x`, `kasmvnc`, `davfs2`, `tini`. No config wired
        yet — image just has the binaries available.
- [x] 4.2 `engines/dosbox-x/entrypoint.sh` is a stub that prints
        "ash-nazg dosbox-x engine container — wiring TBD" and exits 0.
        The wiring change replaces this.
- [x] 4.3 `engines/dosbox-x/README.md` describes the image's role and
        intended interface contract (env vars expected, ports exposed,
        mount points).

## 5. Frontend scaffold

- [x] 5.1 `frontend/` directory bootstrapped with Vite + Vue 3 + TypeScript.
        See section 12 for the full Nextcloud library set.
- [x] 5.2 `frontend/src/IframeHost.vue` is an empty Vue component that
        renders a placeholder div where the KasmVNC iframe will go.
- [x] 5.3 `frontend/package.json` build script outputs to
        `host/static/` so the host container serves the frontend bundle.

## 6. Nextcloud app metadata

- [x] 6.1 `appinfo/info.xml` declaring: id `ash-nazg`, name "Ash Nazg",
        summary one-line, description multi-line (English + Dutch),
        category `tools`, AppAPI dependency, `<external-app>` block with
        `<docker-install>` containing pinned tag (never `latest`),
        required scopes FILES + AUDIT_LOGS + NOTIFICATIONS,
        `<dependencies><nextcloud min-version="30"/></dependencies>`.
- [x] 6.2 Validate `info.xml` against
        `https://apps.nextcloud.com/schema/apps/info.xsd` in CI; merge
        blocked if validation fails. Implemented as
        `scripts/verify-info-xml.sh` (XSD + AppAPI rule checks: image-tag
        not `latest`, image-tag matches semver, required `<external-app>`
        subelements, `<scopes>/<value>` allowlist) plus the
        `verify-info-xml.yml` workflow that runs the script on every PR.
- [x] 6.3 `appinfo/screenshots/` with 3 placeholder PNGs at the App
        Store-required dimensions (real screenshots come after demo
        works).
- [x] 6.4 `l10n/en.json` and `l10n/nl.json` with at least:
        app name, summary, description, settings page name and
        description, the file action display name, the "not yet wired"
        toast text, the self-check button label.

## 7. CI plumbing

- [x] 7.1 `.github/workflows/build-host.yml`: on push to main and on tag,
        builds `ash-nazg-host` multi-arch (amd64+arm64), pushes to GHCR.
        Uses `docker/build-push-action`.
- [x] 7.2 `.github/workflows/build-engine-dosbox.yml`: same for the
        engine image.
- [x] 7.3 `.github/workflows/test.yml`: runs `pytest` on the host code,
        `npm run lint && npm run build` on the frontend. Required for PR
        merges.
- [x] 7.4 `.github/workflows/openspec-validate.yml`: runs `openspec validate`
        against any change folder touched in a PR.
- [x] 7.5 `scripts/verify-against-nextcloud.sh` placeholder + the
        `nextcloud-integration.yml` workflow that runs it on tag pushes
        and `workflow_dispatch`. Currently exits 0 with a TODO log;
        real ephemeral-Nextcloud flow lands in a follow-up change. This
        is the level-3 verifier per `docs/testing.md`.
- [x] 7.6 `docs/testing.md` documents the three verifier layers
        (level 1 per-commit, level 2 per-PR, level 3 per-tag) and maps
        each spec requirement to the layer that enforces it.

## 8. Docs scaffolding

- [x] 8.1 `docs/installation.md` — placeholder explaining HaRP requirement,
        admin install steps (App Store install, enable in admin UI).
        Marked "draft — needs end-to-end test".
- [x] 8.2 `docs/user-guide.md` — placeholder for "how to upload and run
        a binary". Marked "draft".
- [x] 8.3 `docs/security-model.md` — written now (not placeholder),
        capturing the design.md security posture for non-OpenSpec
        readers.
- [x] 8.4 `docs/bring-your-own-content.md` — written now, explaining
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

## 11. Nextcloud distribution + admin settings

- [x] 11.1 `host/src/ash_nazg/admin_settings.py`: a FastAPI router that
        serves the admin settings page route declared in `info.xml`.
        Renders an HTML shell that mounts the Vue settings component
        from `host/static/`.
- [x] 11.2 `host/src/ash_nazg/initial_state.py`: a helper that builds
        the JSON config blob for `@nextcloud/initial-state` to load on
        page mount. In this scaffolding change it returns hardcoded
        defaults; later changes wire it to persistent storage.
- [x] 11.3 `frontend/src/AdminSettings.vue`: top-level
        `<NcSettingsSection>` rendering placeholder controls — engine
        toggle for dosbox-x (default disabled), memory limit input,
        idle timeout input, "Test installation" button. Save action is
        a stub that toasts "saved (not yet persisted)".
- [x] 11.4 `host/src/ash_nazg/selftest.py`: a stub `/selftest` endpoint
        that returns a JSON of four checks, all currently returning
        `status: "skipped — not yet implemented"`. Wiring is the next
        change.
- [x] 11.5 `docs/installation.md`: walkthrough of the App Store install
        flow, including the HaRP requirement, expected install duration,
        and how to verify success via the self-check button.
        Marked "draft until end-to-end test on a real Nextcloud".
- [x] 11.6 CI gate: a workflow that, on tag push, verifies the matching
        image exists in GHCR before allowing the App Store submission
        workflow to proceed.

## 12. Frontend Nextcloud-integration

- [x] 12.1 `frontend/package.json` declares all required `@nextcloud/*`
        packages at versions compatible with Nextcloud 30+:
        `@nextcloud/vue`, `@nextcloud/files`, `@nextcloud/router`,
        `@nextcloud/axios`, `@nextcloud/dialogs`, `@nextcloud/auth`,
        `@nextcloud/event-bus`, `@nextcloud/l10n`,
        `@nextcloud/initial-state`.
- [x] 12.2 ESLint config rule that blocks raw `fetch()` and direct
        `axios` imports in source code; enforces `@nextcloud/axios`.
- [x] 12.3 ESLint config rule that flags hardcoded English strings in
        Vue templates; enforces wrapping in `t('ash-nazg', '...')`.
- [x] 12.4 `frontend/src/files-action.ts`: registers the file action
        via `registerFileAction()` from `@nextcloud/files`. The
        `enabled` predicate checks admin group membership via
        `@nextcloud/auth` + a capabilities lookup, mime type, and size
        limit. The `exec` is a stub that emits a `ash-nazg:run-requested`
        event on `@nextcloud/event-bus` and shows a toast via
        `@nextcloud/dialogs`.
- [x] 12.5 `frontend/src/IframeHost.vue`: empty Vue component covered
        in 5.2; here add `@nextcloud/dialogs` import for future error
        display.
- [x] 12.6 Build script in `frontend/package.json` outputs to
        `host/static/` with proper hashing for cache-busting.
        The output filename SHALL include a content hash; the host
        container's Jinja template SHALL inject the current filename
        rather than a fixed name.

# Changelog

All notable changes to Ash Nazg will be recorded here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the
project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

This file is part of the project's audit trail. Every session that
touches the repository should leave a dated entry below describing
what changed and why.

## [Unreleased]

### Added — 2026-05-08 — `init-mvp-runtime` change scaffolding

OpenSpec change `init-mvp-runtime` initialised. Greenfield repo for
the Ash Nazg ExApp.

- `openspec/` tree with `config.yaml`, the `init-mvp-runtime`
  change folder, six per-capability spec deltas:
  `detection`, `engines`, `files-integration`, `sandbox`,
  `nextcloud-distribution`, `nextcloud-frontend`.
- Repo skeleton: `LICENSE` (AGPL-3.0), `THIRD_PARTY_NOTICES.md`,
  `SECURITY.md`, `CONTRIBUTING.md`, `.gitignore`, `.editorconfig`,
  `CHANGELOG.md` (this file). `README.md` was already present.
- AppAPI scopes finalised as **FILES + AUDIT_LOGS + NOTIFICATIONS**.
  An earlier draft of `proposal.md` listed `AI_PROVIDERS` — that
  scope is irrelevant for a runtime host (it is for TaskProcessing
  AI providers) and has been replaced with `NOTIFICATIONS`, which
  matches the actual need (admin alerts on engine discovery,
  self-check failures, session kills).

### Added — 2026-05-08 — Host container scaffold

`host/` Python package laid out per task §3 of `init-mvp-runtime`.

- `host/pyproject.toml` — Python 3.12, FastAPI ≥0.115, uvicorn,
  httpx, pydantic v2. uv-managed. Ruff + mypy + pytest configured.
- `host/src/ash_nazg/main.py` — FastAPI app exposing `/health`,
  `/heartbeat` (text/plain `ok`), and a `/run` stub that returns
  `501 not_implemented`. Dispatcher logic intentionally absent until
  the `wire-dosbox-engine` change.
- `host/src/ash_nazg/appapi.py` — registration-handshake skeleton.
  Declares `APP_ID = "ash-nazg"` and `REQUIRED_SCOPES = (FILES,
  AUDIT_LOGS, NOTIFICATIONS)`. The actual handshake call raises
  `NotImplementedError` until the next change.
- `host/src/ash_nazg/engines/__init__.py` — `Engine` Protocol plus
  `FileMeta` and `SessionConfig` Pydantic models. Field set on
  `SessionConfig` matches the `engines` capability spec exactly so
  reviewers can grep one to the other.
- `host/Dockerfile` — multi-stage. Stage 1 bootstraps `uv` via pinned
  `pip install`, then `uv sync --frozen --no-dev` (with a noisy
  warning fallback when no lockfile exists yet). Stage 2 runs as a
  non-root `app` user (uid 1000), with a HEALTHCHECK that probes
  `/health`.
- `host/.dockerignore` — excludes venv, caches, tests, git metadata.
- `host/tests/test_health.py` — three pytest cases covering the
  three scaffold endpoints. Slightly more than the spec asked for
  ("a single passing test"), kept boring and assertive.

### Added — 2026-05-08 — Host-side admin settings + self-test stub (§11)

Per task §11.1, §11.2, §11.4, §11.5, §11.6. Closes the host-side
half of the Nextcloud-distribution capability.

#### `selftest.py` — fixed JSON shape, all skipped

`POST /selftest` returns the canonical four-check shape from
`nextcloud-distribution/spec.md` → *Self-check passes on healthy
install*:

```json
{
  "checks": [
    {"id": "host-health",         "status": "skipped", "message": "not yet implemented"},
    {"id": "engines-registered",  "status": "skipped", "message": "not yet implemented"},
    {"id": "deploy-daemon-spawn", "status": "skipped", "message": "not yet implemented"},
    {"id": "audit-log-write",     "status": "skipped", "message": "not yet implemented"}
  ],
  "overall": "skipped"
}
```

Pydantic-modelled (`SelfTestReport`, `CheckResult`,
`Literal["ok", "fail", "skipped"]` for the status enum). Check IDs
and order are normative — the wiring change swaps values, never
the schema. `tests/test_health.py` adds an assertion that locks
the IDs and order so a future drift fails CI.

#### `initial_state.py` — Pydantic, never a loose dict

`AdminInitialState` is the typed blob the frontend's
`@nextcloud/initial-state` `loadState()` reads. Fields:
`app_id`, `app_version`, `engines: dict[str, EngineDefaults]`,
`audit_event_prefix`, `selftest_endpoint`. `EngineDefaults` carries
`enabled` (default False — newly discovered engines are admin-opt-in
per the engines spec), `memory_limit_mb`, `idle_timeout_seconds`.
Defaults track the dosbox-x SessionConfig (1024 MB, 900 s).
Pydantic gives the frontend a JSON-Schema export path for
TypeScript typings — no parallel hand-typed interfaces.

#### `admin_settings.py` — HTML shell + initial-state injection

`GET /admin/settings` renders the page that the AppAPI route in
`info.xml` will point at. The shell:

- emits `<input type="hidden" id="initial-state-ash_nazg-config"
  value="<base64-json>">` per the Nextcloud `loadState()`
  convention;
- renders `<div id="ash-nazg-admin-settings"></div>` as the Vue
  mount target;
- reads `host/static/manifest.json` (vite output) to inject the
  hashed `<script>` and `<link rel=stylesheet>` tags for the
  `admin-settings` entry; if the manifest is missing it renders a
  visible-but-non-fatal "frontend bundle not built yet" warning.

`main.py` includes both routers and conditionally mounts
`/static` over `host/static/` when that directory exists. Choosing
`APIRouter` + a single FastAPI app over `app.mount(...)` keeps
middleware, OpenAPI, and lifespan unified — `mount` is the right
tool for embedding a foreign ASGI app, not for splitting routes
across files.

`tests/test_health.py` grows two cases: the self-test shape lock
described above, and an `/admin/settings` smoke test that the
shell carries the initial-state input, the mount div, and either
a script tag or the not-built warning.

#### `verify-images-published.yml` — App Store submission gate

Runs on `v*.*.*` tags and `workflow_dispatch` (with an optional
`tag` input). For both `ash-nazg-host` and `ash-nazg-dosbox-x`
under `ghcr.io/<owner>/`, runs `docker manifest inspect` against
the version derived from the tag. Fails the workflow if either
manifest is missing, with an explicit error pointing at the
build-host / build-engine workflows.

Any future App Store submission workflow MUST declare
`needs: [verify-images-published]` so it cannot run before this
gate is green. The gate authenticates with `GITHUB_TOKEN`
(read-only on packages is enough; no PAT, no manual secret).

#### `docs/installation.md` — table of self-check IDs

Added an explicit table listing the four `host-health`,
`engines-registered`, `deploy-daemon-spawn`, `audit-log-write`
check IDs with one-line semantics, plus a note that the scaffold
returns `skipped` for all four. Doc still marked DRAFT until the
end-to-end flow exists.

#### Spec consistency tweak

Audit-event names in `specs/sandbox/spec.md`
(`event: ash_nazg.execution`),
`specs/nextcloud-distribution/spec.md`
(`event: ash_nazg.selftest`), and `design.md`
(`event: ash_nazg.execution`) updated from `ash-nazg.*` to
`ash_nazg.*`, matching the renamed app id. The audit-log
documentation in `docs/security-model.md` already used the new
form.

### Added — 2026-05-08 — Docs scaffolding (§8)

Two written-in-full and two drafts.

- **`docs/security-model.md` (written, not draft).** Synthesis of
  `design.md` § *Security posture* and the `sandbox` capability
  spec into an audit-friendly form. Three sandbox layers (admin
  gating, container limits, scoped WebDAV token) each table-mapped
  to the spec requirement that enforces them. Audit-log schema
  with field-by-field coverage. "What this does NOT protect
  against" section names six explicit out-of-scope scenarios
  (malicious admin, engine-binary RCE, kernel escape, side
  channels, exfil-via-WebDAV, multi-tenant). Final layered
  enforcement → verifier mapping ties each promise to the level
  that enforces it.
- **`docs/bring-your-own-content.md` (written, not draft).** One
  page, "we're the runtime; your software is yours". Three
  categories of legitimate sources (own licence, OSS, homebrew),
  honest paragraph on the abandonware grey zone, high-level
  conversion shape (floppies/CDs → .img → upload → DOSBox-X). No
  step-by-step procedure here — that belongs in `user-guide.md`.
- **`docs/installation.md` (DRAFT marker).** HaRP requirement, NC
  30 + AppAPI 5.x floor, admin install sketch, and a *Verifying
  it works* section with three things you can actually run today
  (verify-info-xml, host `/health`, engine binary check). Notes
  that the end-to-end flow does not yet work.
- **`docs/user-guide.md` (DRAFT marker).** Admin-only execution,
  upload→right-click→Run flow as designed, save-where-where table
  (`/mnt/files` persists, `/tmp` doesn't, root is read-only),
  v1 limitations list (one engine, no audio, no GPU, no
  clipboard).

Per the user's guidance, the installation and user guides are
deliberately marked draft until `wire-dosbox-engine` lets us
verify them against a real flow.

### Changed — 2026-05-08 — Drop XSD heuristic; rename NC app id to `ash_nazg`

Two related changes that surfaced together while tightening the
Level-2 verifier.

#### `verify-info-xml.sh` — boring strip-and-validate

Replaced the previous "validate, then grep over xmllint output to
forgive the AppAPI extension" heuristic with a structural approach:
strip every `<external-app>` block via Python stdlib `xml.etree`,
validate the canonical body unconditionally against the NC XSD.
The grep heuristic was clever and would have silently broken if
xmllint changed its error wording. The `<external-app>` block is
now explicitly the responsibility of Level-3
(`verify-against-nextcloud.sh`), which the script's TODO comment
notes for the wiring change.

#### NC app id renamed `ash-nazg` → `ash_nazg`

The newly-strict Level-2 verifier immediately caught a real bug
the heuristic was hiding: the canonical NC `info.xsd` constrains
`<id>` to `[a-z]+[a-z0-9_]*[a-z0-9]+` — **no hyphens**. The id
`ash-nazg` would have been rejected at App Store submission.

Renamed to `ash_nazg` (NC convention; cf. `password_policy`,
`twofactor_totp`). Scope kept tight — only the literal NC app id
changed:

- `appinfo/info.xml`: `<id>`
- `host/src/ash_nazg/appapi.py`: `APP_ID`
- `host/tests/test_health.py`: `/health` response assertion
- `frontend/src/files-action.ts`: `APP_ID`, `FileAction.id`
  (`ash_nazg-run`), event-bus name (`ash_nazg:run-requested`)
- `frontend/src/AdminSettings.vue`: `APP_ID` and all 8
  `t('...', '...')` first-arg references
- Live doc/comment refs updated for accuracy
  (`docs/testing.md` and `verify-against-nextcloud.sh` `occ`
  commands; `frontend/.eslintrc.cjs` and `frontend/README.md`
  inline `t('...')` examples)

**Deliberately NOT changed** — these were never the NC app id:
- Repo name `MWest2020/ash-nazg` and all GitHub URLs
- OCI image names (`ghcr.io/.../ash-nazg-host`,
  `ash-nazg-dosbox-x`)
- Display name "Ash Nazg" in user-facing strings and translation
  values
- npm package name `ash-nazg-frontend`
- CSS classes and DOM ids (kebab-case is conventional in CSS;
  `#ash-nazg-admin-settings`, `.ash-nazg-iframe-host`, etc.)
- Earlier CHANGELOG entries — they accurately describe the prior
  state and aren't rewritten retroactively.

After the rename the verifier passes cleanly: XSD validation
green, image-tag pinned (`0.0.0-scaffold`), all three scopes on
the AppAPI allowlist.

### Added — 2026-05-08 — CI plumbing + three-layer verifier system

Per task §7 plus an expansion to §6.2 + new §7.5 / §7.6 that
introduces an explicit three-level verification ladder. Rationale:
the original `init-mvp-runtime` proposal had Level-1 (per-commit
unit tests) and a vague "App Store schema check" — an implicit
"we'll verify it works" gap before submission. The expansion makes
that gap explicit, scripted, and re-runnable.

#### Verifier layers (lands in `docs/testing.md`)

| Level | When                  | Scope                                  |
|-------|-----------------------|----------------------------------------|
| 1     | per-commit / PR       | code-local: pytest, ruff, vue-tsc, eslint, vite build, openspec validate |
| 2     | per-PR                | metadata + invariants: XSD + AppAPI rules over info.xml |
| 3     | per-tag / dispatch    | end-to-end: ephemeral Nextcloud install (placeholder until follow-up change) |

#### New scripts

- `scripts/verify-info-xml.sh` (executable) — Level 2. Fetches and
  caches the canonical NC `info.xsd`, runs `xmllint --schema`, then
  runs four AppAPI rule checks: `<image-tag>` present and not
  `latest`; image-tag matches `^\d+\.\d+\.\d+([-+][0-9A-Za-z.+-]+)?$`;
  every required `<external-app>` subelement present; every declared
  scope on a maintained allowlist (`FILES`, `AUDIT_LOGS`,
  `NOTIFICATIONS`, plus 14 other documented AppAPI scopes). Tolerates
  the canonical XSD's lack of awareness of `<external-app>` by
  triaging xmllint output. Smoke-tested locally against the current
  `appinfo/info.xml` — all checks pass.
- `scripts/verify-against-nextcloud.sh` (executable) — Level 3
  placeholder. Logs a marked TODO and exits 0. Will become the App
  Store submission gate once the ephemeral-Nextcloud flow lands.

#### New workflows

- `.github/workflows/build-host.yml` — multi-arch buildx (amd64 +
  arm64) of `host/`. PRs build only; pushes to `main` and tag pushes
  push to `ghcr.io/<owner>/ash-nazg-host` with metadata-action tags
  (semver, branch, sha-prefixed). Provenance + SBOM enabled.
- `.github/workflows/build-engine-dosbox.yml` — same for
  `engines/dosbox-x/`. Pins `KASMVNC_VERSION=1.4.0` as a workflow env
  var (kept in sync with the Dockerfile default; verified
  2026-05-08).
- `.github/workflows/test.yml` — Level 1. Two jobs: `host-pytest`
  (uv 0.5.6 + ruff + pytest) and `frontend-build` (Node 22 +
  `npm ci --ignore-scripts` + `npm audit signatures` + typecheck +
  lint + build). The frontend job warns and exits 0 if no
  `package-lock.json` exists yet (first-run grace period, never
  silently skipped — the warning is annotated in the GitHub UI).
- `.github/workflows/openspec-validate.yml` — runs
  `openspec validate` against every in-flight change folder. Fails
  the workflow if any folder fails validation; doesn't short-circuit
  on first failure so you see the full picture.
- `.github/workflows/verify-info-xml.yml` — Level 2. Installs
  `libxml2-utils`, caches the fetched XSD, runs the verifier script.
- `.github/workflows/nextcloud-integration.yml` — Level 3. Runs
  only on `v*.*.*` tag pushes and `workflow_dispatch` — never on PR.
  Calls the placeholder verifier; will become the gate once the
  ephemeral-Nextcloud flow lands.

#### Docs

- `docs/testing.md` — explains the three layers, lists which spec
  requirement is covered by which layer, gives the local-run
  commands for each, and explicitly invites filing a CI/local-dev
  parity bug if a CI failure can't be reproduced locally.

### Added — 2026-05-08 — App Store metadata + i18n bundles

- `appinfo/info.xml` — full Nextcloud App Store manifest. English +
  Dutch `<name>`, `<summary>`, `<description>`. `<licence>agpl`,
  `<category>tools`, `<dependencies><nextcloud min-version="30"
  max-version="32"/></dependencies>`. Three `<screenshot>` URLs
  pointing at `appinfo/screenshots/0[1-3]-*.png` on `main`. AppAPI
  ExApp block declares `ghcr.io/mwest2020/ash-nazg-host` with the
  pinned `0.0.0-scaffold` tag (never `latest`), `<scopes>` =
  FILES / AUDIT_LOGS / NOTIFICATIONS, `<protocol>http`,
  `<port>8080`, `<system>false`, `<translations-folder>/app/l10n`.
  XSD validation deferred to the §6.2 CI workflow (lands in
  Batch G).
- `appinfo/screenshots/0[1-3]-*.png` — 1×1 transparent PNGs (70 B
  each) placed via `base64 -d`. They satisfy the literal
  "placeholder PNG" requirement; replacement with real 1280×800
  captures is the responsibility of the `appstore-v1-submission`
  change.
- `appinfo/screenshots/README.md` — documents the placeholder
  posture and the App Store dimension expectations to verify at
  submission time.
- `l10n/en.json` and `l10n/nl.json` — translation bundles in the
  Nextcloud-canonical `{translations, pluralForm}` JSON shape. Cover
  every string in the frontend that is wrapped in
  `t('ash-nazg', ...)` plus the app metadata strings (name,
  summary, settings description). Both ship the standard
  `nplurals=2; plural=(n != 1);` plural form.

### Added — 2026-05-08 — Frontend scaffold (Vite + Vue 3 + TS, no install)

`frontend/` package laid out per tasks §5, §11.3, §12. Files only —
**no `npm install` was executed in this session** per the
supply-chain rule. The first `npm install --ignore-scripts
--package-lock-only` is left for a human; subsequent installs use
`npm ci --ignore-scripts`.

- `frontend/package.json` — Vue 3.4+, Vite 5.x, TypeScript 5.4+,
  vue-tsc 2.x, Node ≥22, ESLint 8.x. Full `@nextcloud/*` set
  required by §12.1: `auth`, `axios`, `dialogs`, `event-bus`,
  `files`, `initial-state`, `l10n`, `router`, `vue`.
- `frontend/vite.config.ts` — multi-entry build (`files-action`,
  `admin-settings`), output to `../host/static/`, content-hashed
  filenames, manifest.json emitted for the host's template injection.
- `frontend/tsconfig.json` — `strict: true` with all the strict-
  family extras (`noUnusedLocals`, `noUnusedParameters`,
  `noImplicitReturns`, `exactOptionalPropertyTypes`,
  `noImplicitOverride`).
- `frontend/.eslintrc.cjs` — extends `@nextcloud`, plus three
  project rules: `no-restricted-globals` blocks `fetch`,
  `no-restricted-imports` blocks `axios`,
  `vue/no-bare-strings-in-template` enforces `t('ash-nazg', '...')`.
- `frontend/src/files-action.ts` — `FileAction` registered via
  `registerFileAction()`. Enabled predicate: admin gate (stub —
  the user object lookup needs a capabilities call in the wiring
  change), single selection, ≤100 MB, `.exe`/`.com`/`.bat`
  extension. `exec` toasts via `@nextcloud/dialogs` and emits
  `ash-nazg:run-requested` on `@nextcloud/event-bus`.
- `frontend/src/IframeHost.vue` — minimal placeholder that takes
  `sessionId` and `streamUrl` props and renders a labelled `<dl>`.
  Re-exports `showError` from `@nextcloud/dialogs` so the wiring
  change has its error surface ready (§12.5).
- `frontend/src/AdminSettings.vue` — `NcSettingsSection` with the
  dosbox-x engine toggle (defaults off per the engines spec),
  numeric inputs for memory (1024 MB) and idle timeout (900 s)
  matching the engines-spec dosbox-x SessionConfig defaults,
  Save and Test buttons that both toast (no persistence yet).
  Lands §11.3 as a side-effect of wiring the frontend bundles.
- `frontend/src/admin-settings-main.ts` — entry point that mounts
  AdminSettings into `#ash-nazg-admin-settings`.
- `frontend/env.d.ts` — Vue SFC + Vite client type shims.
- `frontend/.gitignore`, `frontend/README.md` — local hygiene and
  the `npm ci --ignore-scripts` bootstrap walkthrough.

### Changed — 2026-05-08 — Pin KasmVNC to verified upstream tag, park architectural choice

- `engines/dosbox-x/Dockerfile` — `KASMVNC_VERSION` default bumped
  from the placeholder `1.3.2` to **`1.4.0`**, the actual current
  upstream release (verified 2026-05-08 against the GitHub releases
  API; both `kasmvncserver_bookworm_1.4.0_amd64.deb` and `..._arm64.deb`
  confirmed present at `/releases/download/v1.4.0/`).
- `engines/dosbox-x/README.md` — new "Open architectural questions"
  section documenting two parked decisions for the
  `wire-dosbox-engine` change: (Q1) keep the `.deb` download path or
  switch the base image to `kasmweb/core-debian-bookworm:1.18.0`,
  and (Q2) integrity verification for the `.deb` if Q1 lands on
  download. Both paths are reachable from the current scaffold
  without rework, so the choice is parked, not preempted.

### Added — 2026-05-08 — DOSBox-X engine container scaffold

`engines/dosbox-x/` per task §4 of `init-mvp-runtime`. Image builds
and contains the binaries; entrypoint is a no-op stub.

- `engines/dosbox-x/Dockerfile` — `debian:12-slim` base. Installs
  `dosbox-x`, `davfs2`, `tini`, `ca-certificates`, `curl` from
  Debian repos. KasmVNC is fetched as a pinned `.deb` from the
  upstream GitHub release (`KASMVNC_VERSION=1.3.2` build arg);
  multi-arch via `TARGETARCH`. Non-root `app` user (uid 1000)
  with `davfs2` group membership. `/mnt/files` directory created
  and chowned for the WebDAV mount. Port 6901 exposed. tini as
  PID 1.
- `engines/dosbox-x/entrypoint.sh` — `set -euo pipefail`, prints
  the exact wiring-TBD message from the spec and exits 0. Replaced
  by `wire-dosbox-engine`.
- `engines/dosbox-x/README.md` — documents the contract surfaces
  the wiring change will hook up: env vars (`NEXTCLOUD_URL`,
  `APP_TOKEN`, `USER_ID`, `FILE_PATH`, `KASMVNC_PASSWORD`,
  optional `IDLE_TIMEOUT_SECONDS`), port `6901`, mount paths,
  resource posture (1 CPU / 1024 MB / 900 s idle / no host net /
  read-only rootfs), build instructions, and an explicit "what is
  intentionally NOT here" section to call out the boundary
  (no profiles, no proprietary content, no persistent state).

KasmVNC `.deb` URL pattern depends on the upstream release naming
convention staying `kasmvncserver_bookworm_<version>_<arch>.deb`. A
verification step belongs in `wire-dosbox-engine` (sha256 pin or
mirror to a controlled artifact store).

### Fixed — 2026-05-08 — OpenSpec validation errors

Four spec requirements failed `openspec validate init-mvp-runtime`
with "must contain SHALL or MUST". Root cause: the validator
inspects only the **first physical line** of a requirement body for
the normative keyword. Each affected requirement had `SHALL` on
line 2+ due to multi-line wrapping. Rewrote each so the SHALL/MUST
clause leads the body. Affected files:

- `specs/detection/spec.md` — "Detection by extension as fallback hint"
- `specs/nextcloud-distribution/spec.md` — "Empty Files state explains usage"
- `specs/nextcloud-frontend/spec.md` — "All user-facing strings translatable"
- `specs/sandbox/spec.md` — "No bundled non-open-source content"

`openspec validate init-mvp-runtime` now reports `is valid`.

---

[Unreleased]: https://github.com/MWest2020/ash-nazg/compare/HEAD...HEAD

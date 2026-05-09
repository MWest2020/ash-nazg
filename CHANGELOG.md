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

### Discovered — 2026-05-09 — AppAPI 5.x manual-install assigns ports, doesn't accept them

Migrated the level-3 verifier's test target to
`nextcloud:32-apache` (AppAPI 5.x bundled, version 32.0.0) per
`wire-dosbox-engine` task §4c. Re-ran
`scripts/verify-against-nextcloud.sh` to validate the new target
before building any handshake code on top.

**Result: the original `wire-dosbox-engine` proposal premise was
wrong.** Documented in
`openspec/changes/wire-dosbox-engine/design.md` § *AppAPI 5.x
manual-install — finding from the test-target migration*.

#### What we believed

> AppAPI 5.x ships a real registration handshake where the ExApp
> advertises its listen port (and routes, scopes, etc.) back to
> AppAPI.

#### What 5.x actually does in `manual-install` mode

- AppAPI **always auto-allocates** the ExApp port (~23000 in our
  test). No `--info-xml`, `<port>`, `--env APP_PORT=`, or
  `host: null` daemon makes it use a different port.
- After `app_api:app:register` returns, AppAPI synchronously
  heartbeats the ExApp at the allocated port.
- Heartbeat fails (host shim listens on 8080) → ExApp ends up
  registered but disabled, with `status.error: "Heartbeat check
  failed"`. `oc_ex_apps_routes` empty.
- Verified with two daemon variants (`host: ash-nazg-host` and
  the AppAPI-canonical `host: null`): same outcome.

#### Implication

The handshake design has to flip:

```
1. ExApp container starts (without knowing its assigned port).
2. occ app_api:app:register …  →  AppAPI allocates port (e.g. 23000)
                                   AppAPI heartbeats ExApp:23000  ⤺ fails
3. Driver reads allocated port + secret from AppAPI; (re)starts
   the ExApp container with APP_PORT and APP_SECRET set.
4. ExApp comes back up listening on the allocated port.
5. ExApp POSTs its routes to AppAPI (separate runtime call).
6. AppAPI proxy URLs start working.
```

In docker-install mode (HaRP, DSP), AppAPI itself spawns the
container in step 3 with the right env vars — no chicken-and-egg.
Manual-install requires either a two-pass deploy, an in-container
port-shim, or migrating to docker-install.

#### Three-way decision parked at task §4.0

`wire-dosbox-engine`'s `tasks.md` now starts with §4.0 *Day-one
architectural decision*:

- **(a)** Two-pass manual-install deploy — operationally honest;
  breaks the one-`docker-compose-up` level-3 invariant.
- **(b)** In-container port-shim — simple level-3, adds a moving
  part inside the host image just to work around an AppAPI default.
- **(c)** docker-install via HaRP — what the App Store will use;
  level-3 verifier becomes heavier (HaRP daemon + docker socket
  + FRP).

Recommended going in: **(c) for production, (a) or (b) for
level-3** — App Store distribution uses HaRP/docker-install; the
level-3 verifier captures whichever manual-install path is least
friction. Decision lands on day-one of the wire-dosbox-engine
implementation session, not in this proposal.

#### Adjustments

- `proposal.md` acceptance criterion #1: rephrased "host shim
  advertises its listen port" to "host shim accepts AppAPI's
  allocated port", with a pointer to the new design.md section.
- `tasks.md` adds §4.0 above the existing §4 handshake tasks.
- `scripts/local-nextcloud-stack.yml` keeps `nextcloud:32-apache`
  (the migration itself is correct; only the assumption about the
  handshake was wrong).

This is exactly the kind of mid-implementation correction that
spec-driven development is supposed to surface — better at design
time than after the wiring code is written.

### Changed — 2026-05-09 — `wire-dosbox-engine` proposal: 3 acceptance additions

Three explicit additions to the `wire-dosbox-engine` change so its
exit criteria are concrete and testable rather than vibes-based.

#### 1. Test target migrates to NC 32 + AppAPI 5.x

`init-mvp-runtime` verified against `nextcloud:30-apache` (AppAPI
4.0.6). `wire-dosbox-engine` migrates to `nextcloud:32-apache` with
AppAPI 5.x because:

- NC 30 is approaching end-of-maintenance; NC 32 is the actively
  supported release.
- AppAPI 5.x has the registration handshake we actually need —
  the ExApp advertises its listen port and routes back to AppAPI
  rather than AppAPI auto-allocating a port that doesn't match
  reality.

Operationally: bump compose tag, possibly tweak
`bootstrap-nextcloud.sh` if AppAPI 5.x has shifted command args,
delete the SQL UPDATE workaround, bump `docs/installation.md`
minimum to NC 32.

NC 30 + AppAPI 4 stays in `CHANGELOG.md` as the historical
first-verified target — record, not support claim.

#### 2. `oc_ex_apps.port` SQL UPDATE retirement is an acceptance criterion

The scaffold's `bootstrap-nextcloud.sh` patches `port=8080` via a
direct DB UPDATE because AppAPI 4.0.6 manual-install auto-
allocates a port (~23000) and provides no override. The wiring
change retires this **explicitly**:

- `appapi.register()` POSTs the host shim's actual listen port to
  AppAPI's `/exapp/register` endpoint. AppAPI 5.x stores it
  verbatim. No DB poke.
- Acceptance: delete the SQL UPDATE block from the bootstrap, re-
  run `verify-against-nextcloud.sh` — all assertions still pass.
- Plus a positive assertion that the AppAPI proxy URL
  `/index.php/apps/app_api/proxy/ash_nazg/health` returns the
  canonical `{"status":"ok",…}` body (not 404). That's the signal
  that route registration also worked.

This converts the "by design 404" caveat in `docs/testing.md`
into a positive test — once the handshake works, the proxy works.

#### 3. `docs/user-guide.md` — explicit DOSBox-X v1 capability scope

New "What DOSBox-X v1 can and cannot run" section, written now
even though it lives in the user guide. Calls out:

- **Can**: MS-DOS / FreeDOS programs, Win 3.0/3.1/3.11, Win16
  binaries, partial Win32s.
- **Cannot**: Win 95/98/ME (out of scope for v1 even though
  DOSBox-X technically supports it), NT/2000/XP/Vista/7/8/10/11,
  modern Win64, Mach-O, ELF, JVM, WASM, DRM-protected modern
  software, GPU-accelerated games, audio.
- **Heuristic**: 1985–1998 release window, "DOS" or "Windows 3.x"
  on the box, ≤100 MB executable, no online-only activation.
- **Future engines** (Wine, RetroArch, JVM, wasmtime) listed as
  "designed for, not in v1" so users know the architecture
  supports the gap.

Same wording will land in the App Store listing's description
when v1 ships. Honest scope upfront prevents support requests
from people expecting a Wine-tier compatibility layer.

`openspec validate wire-dosbox-engine` and `init-mvp-runtime` both
pass after these edits.

### Added — 2026-05-09 — Stage-3 (level-3) verifier — full Nextcloud install smoke

`scripts/verify-against-nextcloud.sh` upgraded from placeholder to a
real driver. It brings up postgres + valkey + nextcloud + ash-nazg-host
via compose, runs the bootstrap, and asserts three scaffold-scope
HTTP contracts hold over a real Nextcloud 30 + AppAPI install. Then
tears the stack down (or keeps it with `KEEP_STACK=1`).

#### What ships

- `scripts/local-nextcloud-stack.yml` — docker-compose recipe.
  Postgres 16 + Valkey 8 (redis-protocol drop-in) + NC 30 (apache
  flavour) + the local `ash-nazg-host:0.0.0-scaffold` image. NC on
  `localhost:8088`. Healthchecks on every service. Credentials are
  local-dev placeholders, not secrets.
- `scripts/bootstrap-nextcloud.sh` — idempotent driver from
  "containers up" to "ExApp registered, enabled, reachable".
  Installs/enables AppAPI, registers a `manual_install` deploy
  daemon with `host=ash-nazg-host` (the compose-network DNS
  name), copies `appinfo/info.xml` into the NC container, and
  registers the ExApp via `app_api:app:register`.
- `scripts/verify-against-nextcloud.sh` — wraps the bootstrap with
  preflight (build the host image if missing), three concrete
  assertions, and a teardown trap. `KEEP_STACK=1` skips teardown
  for inspection.

#### What level-3 proves

| Promise | Verified |
|---|---|
| Manifest accepted by AppAPI | `app_api:app:register` succeeds on the real `info.xml`; AppAPI rejects malformed manifests, ours validates. |
| Single-container ExApp model viable | NC reaches `http://ash-nazg-host:8080/health` over the compose network and gets the canonical `{"status":"ok","app":"ash_nazg",…}` response. |
| Admin settings shell renders | `/admin/settings` serves HTML with the `#ash-nazg-admin-settings` mount div, base64-encoded initial-state, and hashed `<script>` / `<link>` tags from the vite manifest. |
| Self-test JSON shape locked | `/selftest` returns all four canonical check IDs (`host-health`, `engines-registered`, `deploy-daemon-spawn`, `audit-log-write`) in spec order, all `skipped`. |

#### What level-3 deliberately doesn't (yet) cover

The AppAPI proxy URL
`/index.php/apps/app_api/proxy/ash_nazg/health` returns **404 by
design**. AppAPI's proxy is gated by per-route registration; the
ExApp must call back to AppAPI during its registration handshake to
declare which paths are exposed. `host/src/ash_nazg/appapi.py::register()`
currently raises `NotImplementedError` (scaffold scope), so
`oc_ex_apps_routes` is empty and the proxy correctly refuses
everything. Implementing the handshake is owned by `wire-dosbox-engine`.

#### Workaround captured in the bootstrap

AppAPI 4.0.6 (the version bundled with NC 30 at the time) auto-
allocates an ExApp port (~23000) on register; the manual-install
host shim listens on 8080. The bootstrap script directly UPDATEs
`oc_ex_apps.port` to 8080 after register. Documented inline as a
scaffold-scope workaround; `wire-dosbox-engine`'s real handshake
will negotiate the port properly via the AppAPI `setAppDeployState`
flow rather than via a DB poke.

#### Discoveries that informed the bootstrap

- `app_api:daemon:register` has 6 positional args, not 8 (older
  AppAPI examples online list more fields).
- `app_api:app:register --info-xml` wants a real file path inside
  the NC container, not stdin (an earlier `--info-xml=/dev/stdin`
  with a heredoc hung indefinitely).
- `podman-compose exec` flag set differs from Docker-Compose v2;
  preflight uses `dc exec -T <svc> true` instead of
  `dc ps --status running --quiet` for portability.
- The bare `occ app:enable ash_nazg` is the wrong command for
  ExApps — it tries to download from the App Store. Use
  `occ app_api:app:enable`. (We end up doing it via direct DB
  update in the same pass that fixes the port.)

### Fixed — 2026-05-09 — Lint and ruff failures in `test` workflow

`build-host` and `build-engine-dosbox` went green after the earlier
fix; `test` then failed on real lint findings rather than a YAML
parse. Reproduced locally and resolved.

#### Frontend

- **eslint preset wrong for Vue 3 + TypeScript.** The bare
  `'@nextcloud'` extends maps to the Vue 2 + JS preset, which
  doesn't configure `@typescript-eslint/parser` for `<script
  setup>` blocks. `.vue` files with `lang="ts"` raised `Parsing
  error: Unexpected token` on TS-only syntax (generic
  `defineProps`, typed arrow signatures). Switched to
  `'@nextcloud/eslint-config/vue3'` — that preset wires up
  `parser: '@typescript-eslint/parser'` for SFC scripts and adds
  `@vue/eslint-config-typescript/recommended`. Documented the
  reason inline so the bare-`@nextcloud` mistake doesn't recur.
- `frontend/src/files-action.ts` — merged the two
  `from '@nextcloud/files'` imports (`import/no-duplicates`).
  All names are now imported in one statement with `type`
  qualifiers per import.
- `frontend/src/IframeHost.vue` — removed the `export { showError }`
  line. Vue 3's `<script setup>` does not allow ES module exports;
  the rationale ("keeps the diff in streaming-proxy minimal") was
  weak. The streaming change can add the import when it needs it.
- `frontend/src/IframeHost.vue` placeholder labels — wrapped the
  bare `<dt>session</dt>` and `<dt>stream</dt>` in `t('ash_nazg', …)`
  per the project's own `vue/no-bare-strings-in-template` rule.
  Added matching `session`/`stream` entries to `l10n/en.json` and
  `l10n/nl.json` (Dutch: `sessie`, `stream`).
- Auto-fixable formatting (`vue/first-attribute-linebreak`,
  `vue/html-closing-bracket-newline`) — resolved with
  `npm run lint:fix`. Empty JSDoc stubs the auto-fixer added
  were filled in with one-line descriptions for the four
  scaffold helper functions.

After this batch: `npm run lint` returns clean (0 errors, 0
warnings) and `npm run build` produces the bundle to
`host/static/`.

#### Host

- `host/src/ash_nazg/appapi.py` — three ruff findings:
    - **UP037** on `-> "AppApiConfig"`. With
      `from __future__ import annotations` already in the file,
      string-quoting the return type is dead code. Dropped the
      quotes.
    - **S104** on `default="0.0.0.0"` and the matching
      `os.environ.get("APP_HOST", "0.0.0.0")`. Bandit flags binding
      to all interfaces as a security smell, but that's exactly
      what the container does — AppAPI's reverse proxy is the
      external boundary, not the host shim's port. Annotated both
      with `# noqa: S104` and a one-line comment.

`uv run ruff check src tests` now returns "All checks passed".
`uv run pytest -q` reports 5 passed.

### Fixed — 2026-05-09 — CI workflow failures (test.yml, build-host, build-engine-dosbox)

All three failing workflows debugged and fixed locally before re-push.

- **`test.yml` (0 s instant fail).** GitHub Actions reported a
  workflow-file issue. `python3 -c "yaml.safe_load(...)"` showed a
  scanner error at line 28: `name: install deps (extras: dev)` —
  the unquoted colon inside the `name:` value tripped the YAML
  parser. Quoted the entire value. Same root cause as the earlier
  `openspec/config.yaml:96` fix.
- **`build-host.yml` (`COPY static/ /app/static/` not found).**
  CI checks out a clean clone where `host/static/` does not exist
  (it's a frontend build artefact). Refactored `host/Dockerfile`
  into a **3-stage build** that produces the frontend bundle as
  its first stage:
    1. `frontend-build` — `node:22-bookworm-slim`, runs
       `npm ci --ignore-scripts && npm audit signatures &&
       npm run build`. Vite emits to `/work/host/static/`.
    2. `python-build` — `python:3.12-slim-bookworm` + uv sync.
    3. `runtime` — slim Python image, COPYs the bundle from
       `frontend-build`, the venv from `python-build`, plus
       `l10n/` and `appinfo/info.xml`.
  Build context is now repo root (`docker build -f host/Dockerfile .`)
  so the Dockerfile can see both `frontend/` and `host/`.
  `build-host.yml` updated to `context: .`.
  New repo-root `.dockerignore` excludes `.git/`, `node_modules/`,
  `host/static/` (rebuilt inside Docker), specs/docs/scripts dirs,
  and secrets globs. Locally smoke-tested — host image builds
  clean (166 MB) and serves every endpoint with the bundle baked
  in.
- **`build-engine-dosbox.yml` (`Unable to locate package
  dosbox-x`).** Confirmed by trying to build locally: Debian
  Bookworm only ships plain `dosbox`, not `dosbox-x`. The latter
  is in **Ubuntu universe**. Switched the engine base from
  `debian:12-slim` to `ubuntu:24.04` — `dosbox-x` 2024.03.01 is
  available without source builds and KasmVNC v1.4.0 ships
  matching `noble` `.deb` assets, so the OS / streaming layer
  stay coherent. Also `userdel -r ubuntu || true` before creating
  the `app:1000` user, since Ubuntu 24.04's default `ubuntu`
  account already occupies uid/gid 1000. Locally smoke-tested —
  image builds (477 MB), `dosbox-x --version` returns 2024.03.01,
  `kasmvncserver` and `tini` resolve, stub entrypoint prints the
  spec'd "wiring TBD" message and exits 0.



Built the host container locally with podman, ran it, and probed
every endpoint. The smoke caught eight real issues that the
scaffold's lint/typecheck/`openspec validate` had not.

#### Container build path

- `host/pyproject.toml` — removed `readme = "../README.md"`.
  Hatchling validated the path at build time and failed because
  the README is outside the `host/` build context. Fixed by
  dropping the field; the package's narrative lives in repo-root
  README and `host/` is private build content anyway.
- `host/.dockerignore` — un-excluded `static/`. The earlier
  comment said "mounted at runtime, not baked in", but the
  AppStore ExApp model is a single self-contained image; bundling
  the frontend inside the host image is what AppAPI actually
  deploys. The `.dockerignore` now documents this explicitly.
- `host/Dockerfile` — added `COPY static/ /app/static/` in the
  runtime stage. With the `.dockerignore` flip and the COPY,
  `host/static/manifest.json` and the hashed JS/CSS bundles are
  now part of the image at `/app/static/...`.
- `host/uv.lock` — committed for the first time. Generated via
  `uv lock` against `host/pyproject.toml`. 35 resolved packages.
  The Dockerfile's `--frozen` path is now the always-taken branch;
  the warning fallback is dormant.

#### Frontend API drift

The original `frontend/package.json` pinned the @nextcloud/* line
that targets Vue 2.7 + composition API (NC ≤ 30 default frontend).
Bumping to Vue 3 surfaced the actual current Nextcloud-30+
versions:

| Package                   | Old   | New   |
|---------------------------|-------|-------|
| `@nextcloud/vue`          | ^8.21 | ^9.8  |
| `@nextcloud/dialogs`      | ^6.1  | ^7.3  |
| `@nextcloud/files`        | ^3.10 | ^4.0  |
| `@nextcloud/initial-state`| ^2.2  | ^3.0  |
| `@nextcloud/eslint-config`| ^9.0  | ^8.4  |

(`@nextcloud/eslint-config@9` is RC-only on the registry; latest
stable is 8.4.2.)

API changes that came with the bumps:

- `frontend/src/files-action.ts` — `new FileAction({...})` is gone
  in `@nextcloud/files@4`. `registerFileAction` now takes a plain
  object matching the `IFileAction` interface; callbacks receive
  `ActionContext` / `ActionContextSingle` (the node lives at
  `context.nodes[0]`, not as a direct argument). Rewrote the file
  to match.
- `frontend/src/AdminSettings.vue` — `NcButton type="primary"` is
  no longer the visual variant: in `@nextcloud/vue@9`, `type` is
  the HTML button type (`'submit' | 'reset' | 'button'`) and the
  visual variant moved to a `variant` prop. Changed to
  `variant="primary"`.
- `frontend/vite.config.ts` — Vite 5+ writes the manifest to
  `<outDir>/.vite/manifest.json` by default. The host's
  `admin_settings.py` reads `<outDir>/manifest.json`. Set
  `manifest: 'manifest.json'` to keep it at the root and out of
  Vite's internal subdirectory.

#### Lockfiles

- `frontend/package-lock.json` — committed. 626 packages,
  registry signatures verified via `npm audit signatures`. Five
  moderate audit findings, all dev-only (`vite`'s bundled
  `esbuild` dev-server CORS bypass; `@nextcloud/eslint-plugin`'s
  `fast-xml-parser` XML escaping). `npm audit --omit=dev` returns
  zero. Per repo rules these were not auto-fixed; the upgrade
  path is breaking (`vite@8`, `eslint-config@6`) so we wait.

#### Smoke-test result (after fixes)

Every endpoint behaves as designed when the host container runs
locally:

```
GET  /health            → 200 {"status":"ok","app":"ash_nazg","version":"0.0.0"}
GET  /heartbeat         → 200 ok (text/plain)
POST /run               → 501 {"error":"not_implemented", ...}
POST /selftest          → 200 canonical 4-check skipped JSON, IDs in spec order
GET  /admin/settings    → 200 HTML shell with base64 initial-state +
                              hashed bundle <script>/<link> tags
GET  /static/js/...     → 200 25 kB admin-settings JS, 2.9 kB files-action JS
GET  /static/assets/... → 200 17.9 kB CSS
GET  /static/missing    → 404
```

Container runs as non-root `app:1000`. Image is 166 MB.

### Added — 2026-05-09 — Open `wire-dosbox-engine` change (§10.1)

Successor change scaffolded so the next session has a real
landing zone. Created via `openspec new change wire-dosbox-engine`,
then filled in:

- `openspec/changes/wire-dosbox-engine/proposal.md` — Why / What
  Changes / Impact. Scope: dispatcher + engine spawn lifecycle +
  AppAPI registration + real self-test + working engine entrypoint.
  Explicitly out of scope: KasmVNC streaming proxy, admin-settings
  persistence, App Store submission. "Boring valkuil" section
  parks three concrete temptations (custom websocket proxy,
  `docker cp` instead of davfs2, hardcoded `engine == 'dosbox-x'`).
- `openspec/changes/wire-dosbox-engine/design.md` — sequence
  diagram for the first wired Run, engine-registry contract,
  AppAPI registration handshake, self-test wiring table, three
  named valkuilen.
- `openspec/changes/wire-dosbox-engine/tasks.md` — 26 tasks
  across 9 sections (registry, dosbox-x plugin, dispatcher, AppAPI
  register, engine entrypoint, frontend wiring, real self-test,
  tests, hand-off).
- `openspec/changes/wire-dosbox-engine/specs/dispatch/spec.md` —
  two ADDED requirements (dispatcher selects first matching
  enabled engine; self-test reports real per-check status) with a
  total of five scenarios. Each requirement leads with `SHALL` on
  line 1 (validator gotcha already documented in CONTRIBUTING.md).
- `openspec/config.yaml` — fixed a pre-existing YAML parse error
  on line 96 (a colon in a multi-line scalar). Replaced with an
  em-dash separator. The error pre-dated this session but
  surfaced when `openspec new change` ran.

`openspec validate wire-dosbox-engine` passes; the spec is
explicitly DRAFT in every doc heading so the next implementation
session can flesh out tasks and add further spec deltas without
fighting prior commitments.

#### Hand-off (§10.2) — NOT done in this batch

`openspec archive init-mvp-runtime` deliberately not run. Three
items still want a real Nextcloud or explicit approval:

- §0 preflight (AppAPI version verify, HaRP availability check,
  app id reservation).
- §9.1 / §9.3 / §9.4 (docker build of host + engine; in-container
  `/health` 200 check; `npm run build` after first lockfile
  generation).
- §1.1 git push.

Archive moves the specs from `openspec/changes/init-mvp-runtime/`
into the canonical `openspec/specs/` tree. After that any change
to those specs requires a new OpenSpec change. Recommended order:
smoke-test on Docker → push → archive.

#### Tasks ticked

- 9.2 (`openspec validate init-mvp-runtime` passes — verified
  multiple times in this session).
- 9.5 (`info.xml` schema validation wired via
  `scripts/verify-info-xml.sh` and the `verify-info-xml.yml`
  workflow; `occ app:check` portion still wants real-NC
  verification during §9 smoke-testing).
- 10.1 (next change opened with full DRAFT content).

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

---
status: draft
last_reviewed: 2026-07-13
---

# Testing — three verifier layers

Ash Nazg uses three deliberately-separated verifier layers, ordered
by speed, scope, and how often they run. Every spec requirement maps
to exactly one layer; nothing is "covered by intuition".

| Level | When           | Scope                                         | Speed       | Source of truth |
|-------|----------------|-----------------------------------------------|-------------|-----------------|
| **1** | every commit / PR | code-local correctness                     | seconds     | `.github/workflows/test.yml`, `openspec-validate.yml` |
| **2** | every PR       | metadata + cross-component invariants         | seconds     | `.github/workflows/verify-info-xml.yml`, calls `scripts/verify-info-xml.sh` |
| **3** | tag push or manual dispatch | end-to-end install behaviour     | minutes     | `.github/workflows/nextcloud-integration.yml`, calls `scripts/verify-against-nextcloud.sh` |

The point of three layers is that **failures stay local to their
layer**. A typo in a Python module fails Level 1, never Level 3.
A bad scope name in `info.xml` fails Level 2, never Level 1.
A broken AppAPI registration fails Level 3, and only there.

## Level 1 — per-commit, fast

Runs on every push and every PR. Required green before merge.

What it covers:

- `pytest` against the host shim (`host/tests/`).
- `ruff check` for the host code style.
- `vue-tsc --noEmit` and `eslint` against the frontend.
- `vite build` of the frontend (proves the bundle compiles).
- `openspec validate <change-id>` for every in-flight change folder.

What it does **not** cover:

- Whether `info.xml` would be accepted by the App Store schema or by
  AppAPI at deploy time. (Level 2.)
- Whether the ExApp actually registers and serves a working admin
  page on a real Nextcloud. (Level 3.)

## Level 2 — per-PR, medium

Runs on every PR that touches `appinfo/info.xml`,
`scripts/verify-info-xml.sh`, or the workflow itself. Required green
before merge.

What it covers:

- **Canonical XSD validation** against
  `https://apps.nextcloud.com/schema/apps/info.xsd`. The script
  caches the XSD under `.cache/info.xsd` so repeated local runs
  don't hammer apps.nextcloud.com.
- **AppAPI rule checks** that the canonical XSD does *not* know
  about, because `<external-app>` is an AppAPI extension element:
    1. `<image-tag>` is present and is **not** `latest`.
    2. `<image-tag>` matches a permissive semver pattern
       (`X.Y.Z[-prerelease][+build]`).
    3. Every required `<external-app>` subelement is present
       (`registry`, `image`, `image-tag`, `scopes`, `protocol`,
       `port`, `system`).
    4. Every `<scopes>/<value>` entry is on the in-script AppAPI
       scope allowlist. Drift in the allowlist is intentional —
       upstream AppAPI adds scopes occasionally; bumping the script
       is part of the upgrade work.

What it does **not** cover:

- Whether AppAPI would actually accept the manifest at deploy time.
  (Level 3.)
- Whether the declared `<image-tag>` exists in GHCR. There's a
  separate gate for that in §11.6 (CI verifies the image is
  pushed before the App Store submission workflow proceeds).

## Level 3 — per-tag / on-dispatch, slow

Runs only on tag pushes (`v*.*.*`) and manual workflow_dispatch.
**Currently a placeholder** — the script logs a TODO and exits 0.
The implementation lands in a follow-up change.

When fully implemented, what it will cover:

- Spinning up an ephemeral Nextcloud (>= 30) + AppAPI + HaRP +
  postgres + redis stack via docker compose.
- Registering Ash Nazg as an ExApp via
  `occ app_api:app:register ash_nazg ...`.
- HTTP-checking the host shim's `/health`, `/heartbeat`, and (once
  wired) the admin settings page route.
- Tearing the stack down on success or failure.

What it does **not** cover (even when fully implemented):

- The full Commander Keen demo flow with KasmVNC streaming. That
  needs a video-capable runner and is out of scope for the
  install-flow gate. The `streaming-proxy` change owns that.

## Mapping spec requirements to layers

| Spec requirement                                               | Covered by |
|----------------------------------------------------------------|------------|
| `nextcloud-distribution`: AppAPI recognises declared scopes    | Level 2 + Level 3 |
| `nextcloud-distribution`: image tag is concrete, never `latest`| Level 2 |
| `engines`: dosbox-x SessionConfig field set                    | Level 1 (pytest against host) |
| `detection`: magic-byte rules and 415/400 responses            | Level 1 (pytest against host — wired in `wire-dosbox-engine`) |
| `nextcloud-frontend`: every user-facing string is translated   | Level 1 (eslint `vue/no-bare-strings-in-template`) |
| `sandbox`: no bundled non-open-source content in images        | Level 3 (image-content audit; placeholder in Level 1 by review) |
| `nextcloud-distribution`: empty-state hint on first upload     | Level 3 (UI behaviour) |

The mapping is the contract between specs and verifiers. Adding a
new spec requirement requires a corresponding entry here, or an
explicit justification for why it stays "by review only".

## Running the verifiers locally

```bash
# Level 1
cd host && uv run pytest -q
cd frontend && npm run typecheck && npm run lint && npm run build
openspec validate init-mvp-runtime

# Level 2
./scripts/verify-info-xml.sh

# Level 3 (placeholder — currently no-op)
./scripts/verify-against-nextcloud.sh
```

If any of these fail in CI, you should be able to reproduce the
failure locally with the exact command above. If you can't, that's a
CI/local-dev parity bug worth filing.

# init-mvp-runtime

## Why

Nextcloud users today have one path for running custom programs against their
Files: build a full Nextcloud PHP app and publish it to the App Store. That's
absurd for someone with a single legacy program — a DOS-era invoicing tool, an
old Win 3.11 utility, a Commander Keen executable they want to play during
lunch. The bar to "run my program in my Nextcloud" is set so high that nobody
crosses it.

Meanwhile, Nextcloud's ExApp framework (AppAPI, GA since Nextcloud 30) makes it
possible to ship arbitrary container-backed apps via the App Store. And mature
sandbox runtimes (DOSBox-X, Wine, wasmtime, RetroArch, JVM) exist as
well-understood OCI images. The pieces are there; nobody has put them
together.

This change initializes a greenfield repository for **Ash Nazg**: a Nextcloud
ExApp whose sole purpose is to be a runtime host. Users upload binaries to
Files, click Run, and the binary executes in a sandboxed engine with output
streamed to the browser and writes flowing back into Files via WebDAV.

The MVP ships one engine — DOSBox-X — because:

1. It produces the strongest demo (Windows 3.11 Program Manager + Commander
   Keen rendered inside a Nextcloud iframe is a wow-moment that explains the
   whole product in one screenshot).
2. DOSBox-X containers are small (~300 MB), stateless-friendly, and have
   well-understood resource profiles.
3. The plugin-engine architecture must be proven with a real second engine
   later (Wine in v2), so v1 can't take shortcuts that assume "one engine
   forever".

## What Changes

This is the initial scaffolding of an empty repository. Concretely:

- **Repository skeleton**: README, LICENSE (AGPL-3.0 to match Nextcloud
  ecosystem), .gitignore, contribution guide, security policy.
- **OpenSpec scaffolding**: this `init-mvp-runtime` change folder, the
  `openspec/config.yaml`, and the seed specs under `openspec/changes/init-mvp-runtime/specs/`.
- **Host shim skeleton**: `host/` directory with a Python FastAPI ExApp
  scaffold, AppAPI registration handlers, health endpoints. No engine
  dispatch logic yet — that's the next change.
- **DOSBox-X engine container skeleton**: `engines/dosbox-x/` with a
  Dockerfile that builds DOSBox-X + KasmVNC, plus a supervisor entrypoint.
  Empty config; not wired to host yet.
- **Frontend skeleton**: `frontend/` with a Vue 3 + TypeScript app, a
  placeholder Files action registration, and an iframe-host component.
- **Nextcloud app metadata**: `appinfo/info.xml` with the `<external-app>`
  block declaring AppAPI dependency, container reference (placeholder image
  URL), and required scopes (FILES, AUDIT_LOGS, NOTIFICATIONS).
- **CI plumbing**: `.github/workflows/` with build-and-push for both
  containers (host + dosbox-x engine), multi-arch (amd64+arm64), pushing
  to GHCR on tag.
- **Docs scaffolding**: `docs/` with placeholder pages for installation,
  user guide, developer guide, security model.

After this change merges, the next change (`wire-dosbox-engine`) connects
the pieces so the demo flow actually works end-to-end. This change just
makes the scaffolding so subsequent changes have a place to land.

## Discoveries during scaffolding

The scaffolding work surfaced findings that materially shape the
follow-on changes. Recording them here so future readers
understand the architectural state at archive time.

### AppAPI 5.x flipped the handshake direction

The level-3 verifier (`scripts/verify-against-nextcloud.sh`) was
first written against `nextcloud:30-apache` (AppAPI 4.0.6) and
green'd. Migrating it to `nextcloud:32-apache` (AppAPI 5.x)
during the test-target evaluation for `wire-dosbox-engine`
revealed that the assumption *"the ExApp advertises its listen
port to AppAPI"* is wrong for AppAPI 5.x.

In 5.x **manual-install** mode AppAPI **always auto-allocates**
the ExApp port (~23000) and synchronously heartbeats the ExApp
at that address. The ExApp must accept the assigned port; no
flag, env var, or info.xml field overrides this.

Verified with both `host: ash-nazg-host` and the AppAPI-canonical
`host: null` daemon variants. Same outcome:
`oc_ex_apps.port = 23000`, "Heartbeat check failed".

### Manual-install becomes second-rate; level-3 must move to HaRP

The implication for v1 architecture:

- **For production** (App Store distribution): the canonical path
  is **docker-install via HaRP**. AppAPI spawns the ExApp
  container itself with the right env vars, so port allocation
  and heartbeat happen in lockstep. There's no chicken-and-egg.
- **For level-3 verification**: must also move to HaRP.
  Maintaining a manual-install path "just for testing" creates
  two install models that drift; the pain of debugging "works in
  prod, fails in level-3" later is bigger than the upfront cost
  of running HaRP locally.

The level-3 verifier shipped in this scaffold change uses
manual-install with a SQL-UPDATE workaround on
`oc_ex_apps.port` to keep the smoke test viable. That workaround
is documented inline, in the bootstrap script, in
`docs/testing.md`, and as an explicit retirement criterion in
`wire-dosbox-engine/proposal.md`. It exists for **exactly one
release**: this scaffolding change. The next change replaces
both the production install path and the level-3 verifier with
HaRP-based docker-install — and deletes the SQL UPDATE.

### Why this finding belongs here, not in wire-dosbox-engine alone

Two reasons:

1. The scaffolding change ships an artefact (the level-3
   verifier with its SQL workaround) that future readers will
   look at and ask "why is this here?". The honest answer lives
   in this Discoveries section.
2. Better that the architectural correction surfaces at
   spec-time — before `wire-dosbox-engine` writes any wiring
   code — than six months in, when reverting an "advertise port"
   handshake would be a refactor bomb. This is the
   spec-driven-development gain working as intended.

`wire-dosbox-engine` task §4.0 (Day-one architectural decision)
locks in **option (c) — docker-install via HaRP for both
production and level-3**, with the rationale captured in that
change's design.md.

## Impact

**Affected systems:** none (greenfield).

**Created artifacts:**
- New GitHub repo: `MWest2020/ash-nazg` (recommended; final naming up to
  the project owner).
- New OCI images: `ghcr.io/mwest2020/ash-nazg-host` and
  `ghcr.io/mwest2020/ash-nazg-dosbox-x` (placeholders, no functional
  behavior yet).
- New App Store listing: NOT created in this change. App Store submission
  happens after v1 demo is end-to-end functional.

**Dependencies introduced:**
- Runtime: Nextcloud 30+, AppAPI 5+, HaRP deploy daemon.
- Build: Docker buildx, Python 3.12, Node 22 LTS, Go (none yet — host is
  Python).
- Open source components used: DOSBox-X (GPL-2.0), KasmVNC (GPL-3.0),
  davfs2 (GPL-2.0), FastAPI (MIT), Vue 3 (MIT), @nextcloud/vue (AGPL-3.0).

**Boring valkuil:**
The temptation here is to "just write the dispatcher and one engine in one
big change to get to demo faster." Resist it. The dispatcher is the
architectural lynchpin — if v1 hardcodes "engine == dosbox-x" anywhere, v2
will require refactor. This change deliberately stops at scaffolding so
the dispatcher gets its own change with its own review.

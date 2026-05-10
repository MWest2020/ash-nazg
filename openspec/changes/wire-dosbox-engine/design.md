# Design — wire-dosbox-engine

> **Status: DRAFT.** Sketch-level. Concrete contracts (HTTP shapes,
> error envelopes, deploy-daemon API surface) are finalised at the
> start of the implementation session.

## Sequence — first wired Run

```
Browser              Host shim                     Deploy daemon (HaRP)         Engine container
   │                    │                                  │                            │
   │ POST /run ─────────▶                                  │                            │
   │   {file_path}      │                                  │                            │
   │                    │ detect (magic bytes via WebDAV   │                            │
   │                    │   range request, ≤512 bytes)     │                            │
   │                    │                                  │                            │
   │                    │ select engine: dosbox-x          │                            │
   │                    │ build SessionConfig              │                            │
   │                    │                                  │                            │
   │                    │ POST /spawn (image, env, limits) ▶                            │
   │                    │                                  │ start container ───────────▶
   │                    │                                  │                            │ tini → entrypoint
   │                    │                                  │                            │   → davfs2 mount /mnt/files
   │                    │                                  │                            │   → kasmvncserver :6901
   │                    │                                  │                            │   → dosbox-x <FILE_PATH>
   │                    │ ◀── {session_id, host, port}     │                            │
   │ ◀── 200 {session_id}│                                 │                            │
   │                    │                                  │                            │
   │ (poll /sessions/{id}/status …)                        │                            │
```

## Engine registry

- Python entrypoint group: `ash_nazg.engines`
- Each entrypoint resolves to a class implementing the `Engine`
  Protocol from `host/src/ash_nazg/engines/__init__.py`.
- Discovery happens once at host startup. Failures (missing
  attributes, raised exceptions) are logged and the engine is
  skipped — host stays up.
- Admin settings can disable individual engines; the registry
  filters disabled engines out of dispatch.

## AppAPI 5.x manual-install — finding from the test-target migration

The test-target migration to NC 32 + AppAPI 5.x (task §4c) ran the
existing `verify-against-nextcloud.sh` against the new target and
surfaced a real architectural constraint that flips the assumption
this design.md was originally written under.

### What we believed (in the proposal)

> *"AppAPI 5.x ships a real registration handshake where the
> ExApp advertises its listen port (and routes, scopes, etc.) back
> to AppAPI."*

### What AppAPI 5.x actually does

In `manual-install` mode AppAPI **always auto-allocates** the
ExApp port (~23000 in our test). After `app_api:app:register`
returns, AppAPI synchronously heartbeat-checks the ExApp at
`<daemon-host or inferred>:<allocated-port>`. The check fails
loudly when nothing is listening there, but neither the
`--info-xml` block, nor the `<port>` field of `info.xml`, nor the
`--env APP_PORT=...` flag, nor a `host: null` daemon, persuade
AppAPI to use a different port.

Verified with two daemon variants:

| Daemon `host` | Result |
|---|---|
| `ash-nazg-host` (compose DNS) | Register hangs / times out polling `ash-nazg-host:23000` |
| `null` (per AppAPI's own `--help` example) | Same: register completes with `"Heartbeat check failed"`; ExApp registered but disabled |

`oc_ex_apps.port = 23000` in both cases. `oc_ex_apps_routes`
remains empty until the ExApp registers its routes via a separate
runtime call — which it can only do once it's reachable, i.e.
listening on the right port. Chicken and egg.

### Implication for the handshake design

The flow has to be:

```
1. ExApp container starts (without knowing its assigned port).
2. occ app_api:app:register …  →  AppAPI allocates port (e.g. 23000)
                                  AppAPI also generates APP_SECRET
                                  AppAPI heartbeats ExApp:23000  ⤺ fails
3. The driver (bootstrap script or docker-install daemon) reads
   the allocated port + secret from AppAPI and (re)starts the
   ExApp container with APP_PORT and APP_SECRET set accordingly.
4. ExApp comes back up listening on the allocated port; subsequent
   heartbeats succeed; AppAPI marks the ExApp healthy.
5. ExApp now POSTs its routes to AppAPI (separate runtime call).
6. AppAPI proxy URLs start working.
```

For a `docker-install` daemon (HaRP, DSP), AppAPI itself spawns
the container with the right env vars in step 3 — there's no chicken-
and-egg.

For `manual-install`, the operator runs the container, so steps
3–5 require either:

- **a) Two-pass deploy:** register first to get the port, then
  start the container with `APP_PORT=<that>`. Awkward in a
  docker-compose-up world where the container is already running.
- **b) Reverse-proxy shim:** the host container listens on a fixed
  port (8080) and a tiny in-container reverse proxy forwards from
  the AppAPI-allocated port to 8080. Adds complexity but keeps
  compose simple.
- **c) Move to docker-install with HaRP:** the v1-canonical path.
  Requires bringing up HaRP daemon + docker socket, but eliminates
  the port-juggling entirely.

### Decision: (c) — docker-install via HaRP, for both production and level-3

Three options were on the table:

- **(a)** Two-pass manual-install deploy.
- **(b)** In-container port-shim.
- **(c)** docker-install via HaRP.

Decision: **(c) for both paths**. Rationale:

- **One install model is cheaper than two.** Maintaining
  manual-install "just for level-3" creates a dialect that
  drifts from production. The pain of "works in prod, fails in
  level-3" or vice-versa six months in is larger than the
  upfront cost of running HaRP locally.
- **Manual-install is second-rate in AppAPI 5.x.** AppAPI's own
  CLI examples list manual-install last, with `host: null` and
  caveats. The contributors clearly treat docker-install as the
  primary path. We follow the upstream's centre of gravity.
- **The "refactor bomb" risk dominates.** Building wiring code
  on top of a manual-install handshake assumption that we'd
  later have to rework for App Store submission is precisely
  the kind of mid-flight architectural rework spec-driven
  development is meant to prevent.

What this means concretely for `wire-dosbox-engine`:

- The level-3 verifier's compose stack adds an `appapi-harp`
  service. The ash-nazg-host service is no longer started by
  compose — HaRP spawns it via the docker socket on `app:register`.
- The host shim's `appapi.register()` reads `APP_PORT`,
  `APP_SECRET`, `APP_VERSION`, `APP_ID`, `NEXTCLOUD_URL` from env
  vars that **HaRP sets when it spawns the container** (per the
  AppAPI 5.x docker-install convention) and accepts those values
  rather than choosing them.
- Routes are POSTed to AppAPI by the ExApp at startup as the
  second part of the handshake (this part of the original design
  is unchanged — it's the route registration that's still the
  ExApp's responsibility, not the port).

The acceptance criterion *"no DB UPDATE workaround in the
bootstrap"* stays — and now there's no bootstrap-driven port
patching at all, because HaRP handles port allocation directly.

## AppAPI registration handshake (AppAPI 5.x)

Triggered at host startup (FastAPI `lifespan` hook). One handshake
call from the ExApp to AppAPI, replacing several pieces of
post-install hand-holding that 4.0.6 needed.

**Endpoint.** `POST {NEXTCLOUD_URL}/index.php/apps/app_api/api/v1/exapp/register`

**Payload (canonical fields, names per AppAPI 5.x):**

| Field | Purpose | Why we need it |
|---|---|---|
| `appid` | `ash_nazg` | Identity |
| `version` | host shim's version | Matches `<version>` in info.xml |
| `secret` | per-deploy shared secret | AppAPI uses it to sign callbacks back to the ExApp |
| `host` | the host shim's address from AppAPI's POV | For our manual-install model: `ash-nazg-host` (compose DNS name) |
| `port` | what the host shim is **actually** listening on | **Replaces the 4.0.6 DB-poke workaround.** AppAPI stores this verbatim in `oc_ex_apps.port`; no auto-allocation, no UPDATE. |
| `routes` | every URL path the AppAPI proxy may forward | Populates `oc_ex_apps_routes`. Without this the proxy 404s — that was the gap in the level-3 verifier under 4.0.6. |
| `scopes` | requested AppAPI scopes (must match info.xml) | `FILES`, `AUDIT_LOGS`, `NOTIFICATIONS` |
| `external` | true | We're not a docker-install ExApp |

**Behaviour.**

- On `200 OK` from AppAPI → host enters serving state, starts
  accepting `/run` requests.
- On `4xx/5xx` → log the AppAPI response body (helpful for
  diagnosing a misconfigured manifest), retry with exponential
  backoff (5 s, 15 s, 45 s, …) up to 5 minutes, then exit
  non-zero. The compose `restart: unless-stopped` policy (or
  HaRP, in non-manual-install deployments) brings the container
  back.
- On network unreachable (NC not yet up) → same backoff, but the
  error log distinguishes "could not reach AppAPI" from "AppAPI
  rejected our payload" so the operator sees the right thing.

**What this retires from the scaffold.**

- `bootstrap-nextcloud.sh`'s `oc_ex_apps.port` UPDATE — gone, the
  handshake sets the right port directly.
- The "AppAPI proxy 404 by design" caveat in
  `docs/testing.md` — once routes register, the proxy works.
- The placeholder `register()` in `host/src/ash_nazg/appapi.py`
  raising `NotImplementedError`.

**Acceptance signal.** After this lands, deleting the SQL UPDATE
from `bootstrap-nextcloud.sh` and re-running
`scripts/verify-against-nextcloud.sh` produces a working install.
That's the boring-and-verifiable definition of "the handshake is
the source of truth, not the workaround".

## Self-test wiring

Each of the four checks gets a real implementation, while the
JSON shape stays identical:

| id                     | implementation                                                                                  |
|------------------------|--------------------------------------------------------------------------------------------------|
| `host-health`          | `httpx.get('http://127.0.0.1:8080/health')` from inside the host container; status==200.       |
| `engines-registered`   | `len([e for e in registry.enabled_engines()]) >= 1`.                                            |
| `deploy-daemon-spawn`  | `POST /spawn` with a transient sidecar (busybox sleep 1); assert it tears down within 30 s.    |
| `audit-log-write`      | Write an `event: ash_nazg.selftest` entry; assert the AppAPI audit-log API returned 2xx.        |

## Boring valkuil

1. **Custom websocket proxy.** Tempting to write a tiny FastAPI
   websocket relay because "KasmVNC is overkill for DOSBox-X." Don't.
   The streaming-proxy change uses KasmVNC; bypassing creates
   throwaway code that streaming-proxy then deletes.
2. **Skipping the engine entrypoint's WebDAV mount and using
   `docker cp`.** Deceptively simpler, but breaks the "save
   inside the app, see it in Files immediately" UX. Pick davfs2
   from day one.
3. **Hardcoding `engine == 'dosbox-x'` in the dispatcher.** The
   plugin protocol exists exactly so v2 engines slot in without
   touching dispatch. Resist any shortcut that bakes the engine
   name into the dispatcher.

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

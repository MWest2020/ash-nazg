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

## AppAPI registration handshake

- Triggered at host startup (FastAPI `lifespan` hook).
- `POST {NEXTCLOUD_URL}/index.php/apps/app_api/api/v1/exapp/register`
  with `EX_APP_ID`, version, host:port, declared scopes, and the
  AppAPI shared secret.
- On 200 → host enters serving state. On 4xx/5xx → host logs the
  payload, retries with exponential backoff up to 5 minutes, then
  exits non-zero (HaRP will restart it).

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

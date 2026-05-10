# Design — init-mvp-runtime

## Architecture overview

Ash Nazg is composed of three deployable units and one configuration artifact:

```
┌───────────────────────────────────────────────────────────────────────┐
│                       Nextcloud Server                                │
│                                                                       │
│  ┌─────────────────┐     ┌────────────────────────────────────────┐   │
│  │  Nextcloud PHP  │     │            AppAPI / HaRP               │   │
│  │  (core + Files) │◄───►│  (websocket-capable reverse proxy)     │   │
│  └─────────────────┘     └──────────────┬─────────────────────────┘   │
│                                         │                             │
└─────────────────────────────────────────┼─────────────────────────────┘
                                          │
                          ┌───────────────┴────────────────┐
                          │                                │
                          ▼                                ▼
                ┌──────────────────────┐    ┌──────────────────────────┐
                │  Host container      │    │  Engine container        │
                │  ash-nazg-host       │    │  ash-nazg-dosbox-x       │
                │                      │    │                          │
                │  FastAPI shim        │    │  DOSBox-X + KasmVNC      │
                │  - AppAPI register   │    │  - WebDAV mount          │
                │  - file action API   │    │  - websocket stream      │
                │  - dispatcher        │    │                          │
                │  - audit logger      │    │  (one per session)       │
                └──────────────────────┘    └──────────────────────────┘
```

**Frontend**: served by the host container, loaded by Nextcloud as an ExApp
page and as a Files-app extension script. Vue 3 SPA, communicates with the
host via OCS/AppAPI proxy.

**Host container** (`ash-nazg-host`): always-on, lifecycle managed by AppAPI.
Owns the dispatcher logic, audit logging, session state, and engine
lifecycle (spawning/killing engine containers). Stateless across restarts;
session state lives in the AppAPI persistent volume.

**Engine container** (`ash-nazg-dosbox-x`): on-demand, one per active session.
Spawned by the host when a user clicks Run, destroyed on idle timeout or
explicit close. Mounts a slice of the user's Nextcloud Files via WebDAV.
Streams its display output via KasmVNC websocket.

## Sequence — Commander Keen demo flow

```
User                  Files-app           Host container       Engine container
 │                      │                       │                       │
 │ uploads keen1.exe    │                       │                       │
 │─────────────────────►│                       │                       │
 │                      │ (stored in Files)     │                       │
 │                      │                       │                       │
 │ right-click → Run    │                       │                       │
 │─────────────────────►│                       │                       │
 │                      │ POST /run {file_id}   │                       │
 │                      │──────────────────────►│                       │
 │                      │                       │ detect: PE32, MS-DOS  │
 │                      │                       │ select engine: dosbox │
 │                      │                       │                       │
 │                      │                       │ docker run engine ────►│
 │                      │                       │                       │ boot DOSBox-X
 │                      │                       │                       │ mount WebDAV
 │                      │                       │                       │ KasmVNC up
 │                      │  302 → /session/<id>  │                       │
 │                      │◄──────────────────────│                       │
 │                      │                       │                       │
 │ iframe loads stream  │                       │                       │
 │─────────────────────────────────────────────────────────────────────►│
 │ ◄─────────────────── KasmVNC WS stream ──────────────────────────────│
 │                                                                       │
 │ types, plays, F10 quits                                               │
 │ saves screenshot to /Documents/keen.png ─────────────────────────────►│
 │                                                                       │ writes via WebDAV
 │                                                                       │
 │  closes tab → host detects idle → docker stop ◄───────────────────────│
 │                      │                       │ POST audit log        │
 │                      │                       │  to OCS API           │
```

## AppAPI integration points

The host shim registers itself with Nextcloud's AppAPI on first install via
the standard `/exapp/v1/ex-app/register` handshake. It declares:

- **App ID**: `ash-nazg`
- **Required scopes**:
  - `FILES` — to read uploaded binaries and write outputs back
  - `AUDIT_LOGS` — to log execution events
  - `NOTIFICATIONS` — to surface engine errors to the user
- **Webhook subscriptions**: none in MVP. File-watch triggers are out of
  scope; everything is user-initiated.
- **Settings UI**: an admin-only page under Nextcloud Settings →
  Administration → Ash Nazg, where engines are enabled/disabled and
  resource limits set.

The host requests a per-session user token from AppAPI before spawning an
engine container, and passes that token (plus the WebDAV base URL) into
the engine container as environment variables. The engine uses it to
authenticate its WebDAV mount.

## Engine dispatcher contract

Even though MVP only ships one engine, the dispatcher must be defined now
so v2 engines slot in cleanly. Contract:

```python
class Engine(Protocol):
    id: str  # e.g. "dosbox-x"
    image: str  # OCI ref, e.g. "ghcr.io/mwest2020/ash-nazg-dosbox-x:1.0.0"

    def can_handle(self, file_meta: FileMeta) -> bool:
        """Inspect magic bytes + extension. Return True if this engine
        should handle the file. Multiple engines may match; first wins
        in registration order, configurable per install."""

    def session_config(self, file_meta: FileMeta) -> SessionConfig:
        """Return container args, env, mounts, resource limits, and
        the streaming endpoint name."""
```

Engines register themselves at host-container startup via a Python
entrypoint group (`ash_nazg.engines`). Adding a new engine in v2 means
publishing a new package + image; the host doesn't change.

## File mount strategy

Each engine container gets a per-session WebDAV mount of the user's
Nextcloud Files at `/mnt/files`. Implementation: `davfs2` running inside
the engine container, authenticated via the AppAPI-issued user token.

Trade-offs considered:

- **WebDAV via davfs2**: chosen. POSIX-ish semantics, plays well with
  DOSBox-X's filesystem expectations, supports ad-hoc writes during
  session.
- **Pre-copy in / post-copy out**: rejected. Doubles disk use, breaks
  the "save inside the app, see it in Files immediately" UX.
- **Direct OCS API calls from engine**: rejected. Would require the
  engine to be application-aware; defeats the "engines are dumb runtimes"
  principle.

Latency cost: WebDAV adds 20–80ms to file ops. Acceptable for DOSBox-X
which doesn't make many syscalls. Will need re-evaluation when Wine
arrives in v2.

## Streaming layer

KasmVNC is chosen over alternatives:

- **KasmVNC**: chosen. Modern, websocket-native, low-latency, embeds
  cleanly via the kasmweb HTML5 client in an iframe. Active maintenance.
  Permissively licensed (GPL-3.0 for server, MIT for client SDK).
- **noVNC**: viable but older, less performant for high-FPS scenes.
- **Apache Guacamole**: heavyweight, requires guacd daemon, overkill.
- **Xpra**: powerful but its HTML5 client is fragile.

The KasmVNC client lives in the frontend bundle. It connects to the engine
container's websocket via the AppAPI proxy (which is why HaRP is required —
DSP doesn't proxy websockets reliably).

## Security posture

**Admin-only execution in v1.** The Files action that triggers Run is
hidden from non-admin users via Nextcloud's standard permission system.
The host shim re-validates admin status on every Run request — the
frontend hide is UX, not security.

**Resource limits per session container:**
- 1 CPU, 1 GB RAM (cgroup-enforced via Docker run flags)
- No GPU access
- No host network; only the AppAPI proxy network
- Read-only root filesystem; writable scratch at `/tmp` (tmpfs, 256 MB)
- WebDAV mount at `/mnt/files` is the only persistent surface

**Idle timeout:** 15 minutes default. Configurable in admin settings.
On timeout, host sends SIGTERM, waits 30s, then SIGKILL.

**Audit log entry per execution** (written to Nextcloud's audit log):
```
event: ash_nazg.execution
user_id: admin
file_path: /Documents/keen1.exe
file_sha256: ...
engine: dosbox-x
engine_image: ghcr.io/.../ash-nazg-dosbox-x:1.0.0
session_id: <uuid>
started_at: <iso8601>
ended_at: <iso8601>
exit_status: graceful_close | timeout | killed
peak_memory_mb: <int>
cpu_seconds: <float>
```

**Content distribution boundary:** the host container ships zero binaries
that aren't open source. No Win 3.11 image, no ROMs, no BIOS files. The
README and the in-app empty-state UI explain that users provide their own
legally-obtained content.

## What is NOT in this change

This is scaffolding only. Do NOT in this change:

- Implement actual `can_handle()` logic for the dosbox-x engine — that's
  `wire-dosbox-engine`.
- Implement the WebDAV mount inside the engine container — that's
  `engine-files-mount`.
- Implement the KasmVNC websocket proxy through AppAPI — that's
  `streaming-proxy`.
- Implement the admin settings page — that's `admin-settings-ui`.
- Submit to App Store — that's `appstore-v1-submission` (after demo works
  end to end).

Each of those is its own subsequent change. This change only creates the
files in which they will land.

## Boring valkuil

Three places where the temptation to be clever is highest:

1. **Skipping the dispatcher abstraction in MVP "because we only have one
   engine".** Don't. The dispatcher is the architecture; without it,
   adding Wine later is a refactor, not an addition.

2. **Using Docker Socket Proxy because it's simpler than HaRP.** Don't.
   Websocket support is non-negotiable for streaming, and HaRP is the
   path Nextcloud is investing in.

3. **Building a custom streaming protocol "because KasmVNC is overkill
   for DOSBox-X".** Don't. The whole point of the architecture is that
   v2 engines (Wine, GUI emulators) will need real streaming. Use
   KasmVNC from day one.

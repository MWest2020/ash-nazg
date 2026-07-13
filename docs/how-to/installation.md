---
status: draft
last_reviewed: 2026-07-13
---

# Installing Ash Nazg

> **Status: DRAFT.** This guide will be finalised in the batch
> covering the `wire-dosbox-engine` end-to-end demo. Steps below
> are written from the design docs, not from a verified install.
> Expect minor inaccuracies until that change lands; treat this
> as a sketch, not a procedure.

## Requirements

| Component         | Minimum  | Notes                                                                                  |
|-------------------|----------|----------------------------------------------------------------------------------------|
| Nextcloud         | 30       | AppAPI 5.x is GA from Nextcloud 30; earlier versions are NOT supported.               |
| AppAPI            | 5.x      | Install from the App Store before installing Ash Nazg.                                |
| Deploy daemon     | **HaRP** | DSP is **not** supported. Streaming uses websockets, which DSP does not proxy reliably. |
| Container runtime | Docker (or compatible) | Required by HaRP.                                                       |
| Architecture      | linux/amd64 or linux/arm64 | Both host and engine images are multi-arch.                          |

## Steps (sketch — to verify)

1. **Install AppAPI** from the Nextcloud App Store and enable it.
2. **Configure HaRP** as the active deploy daemon. Confirm with:
   ```bash
   occ app_api:daemon:list
   ```
3. **Install Ash Nazg** from the Nextcloud App Store. The first
   install pulls the host container image
   (`ghcr.io/mwest2020/ash-nazg-host:<tag>`). Allow a few minutes
   for the pull on a slow link.
4. **Verify the install** via the admin settings page:
   *Administration → Ash Nazg → Test installation*. The button
   runs the host shim's `/selftest` endpoint and reports four
   checks. All four green = ready.
5. **Enable an engine.** The dosbox-x engine ships **disabled by
   default** (per the engines spec — newly discovered engines are
   admin-opt-in). Toggle it on in the same settings panel.

The self-check returns four named checks in this fixed order:

| Check id              | Verifies                                                  |
|-----------------------|-----------------------------------------------------------|
| `host-health`         | The host shim's `/health` endpoint returns 200.           |
| `engines-registered`  | At least one engine is registered and enabled.            |
| `deploy-daemon-spawn` | HaRP can spawn and tear down a transient sidecar in 30 s. |
| `audit-log-write`     | Writing an `ash_nazg.selftest` event to the audit log succeeds. |

In this scaffold release every check returns
`status: "skipped"`. The `wire-dosbox-engine` change replaces the
per-check logic; the JSON shape stays identical so the frontend
binding is stable.

## Verifying it works

Until the wiring change lands, verification is limited. What you
can do today:

- Confirm `appinfo/info.xml` validates locally:
  ```bash
  ./scripts/verify-info-xml.sh
  ```
- Confirm the host container starts and `/health` returns 200:
  ```bash
  docker run --rm -p 8080:8080 \
      ghcr.io/mwest2020/ash-nazg-host:<tag>
  curl -s http://127.0.0.1:8080/health
  ```
- Confirm the engine container builds and the binaries are
  present:
  ```bash
  docker buildx build --platform linux/amd64 \
      -t ash-nazg-dosbox-x:test \
      engines/dosbox-x/
  docker run --rm -it ash-nazg-dosbox-x:test \
      /usr/bin/dosbox-x --version
  ```

The end-to-end "click Run, see Commander Keen" flow does NOT yet
work. That's `wire-dosbox-engine`.

## What ships in this scaffold

A **scaffold** install — the manifest registers, the host
container responds to `/health` and `/heartbeat`, the admin
settings page renders, and the Files action is registered but
toasts "not yet wired" when clicked. No actual sandbox spawns.
That is intentional; the scaffolding change deliberately stops
short of dispatch logic so the dispatcher gets its own change with
its own review.

## Troubleshooting (placeholder)

To be filled in when the demo flow exists. Expected sections:

- "Install hangs at container pull"
- "AppAPI daemon registration failed"
- "Self-test reports DAEMON-UNREACHABLE"
- "Self-test reports IMAGE-NOT-FOUND"
- "Files action does not appear on `.exe` files"

## Uninstalling

```bash
occ app_api:app:unregister ash_nazg
occ app:remove ash_nazg
```

Removes the manifest registration and the host container. User
Files are untouched (Ash Nazg stores no persistent state of its
own outside the AppAPI volume; sessions are ephemeral).

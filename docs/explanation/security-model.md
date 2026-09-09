---
status: draft
last_reviewed: 2026-07-13
---

# Ash Nazg — Security Model

This document is the authoritative description of Ash Nazg's
security posture. It synthesises the design notes in
`openspec/changes/init-mvp-runtime/design.md` and the normative
requirements in
`openspec/changes/init-mvp-runtime/specs/sandbox/spec.md` into a
form that an admin (or an ISO 27001 / SOC 2 auditor) can navigate
in five minutes.

Each claim links back to the spec requirement that enforces it, so
the audit trail goes:

> docs claim → spec requirement → verifier layer → CI artefact

If a claim here is not backed by a spec requirement, that's a
documentation bug — file it.

## 1. Threat model in one paragraph

Ash Nazg runs **user-supplied, potentially untrusted binaries**
inside a Nextcloud instance. The binary is treated as untrusted
input to the sandbox. Everything else — the host shim, the app image
that carries the emulator, the Nextcloud admin who installed the app —
is in the trusted base. The system protects the rest of the Nextcloud
instance and the Internet at large from the user-supplied binary.
It does **not** protect the Nextcloud instance from a malicious
admin (admin is trusted by design, in v1).

## 2. The three sandbox layers

Defence in depth, three layers. They are not equally strong, and the
page says which is which: Layer 2 is the emulator, and since the engine
ships inside the app container it is the load-bearing one.

### Layer 1 — Nextcloud admin gating

Only admin users can dispatch a binary in v1.

| Claim                                              | Backed by                                                                                                              |
|----------------------------------------------------|------------------------------------------------------------------------------------------------------------------------|
| The Files action is hidden from non-admins.         | UX hide; **not** security. See spec, "Admin-only execution in v1" — frontend hide is documented as UX, not enforcement. |
| The host shim re-validates admin status on every Run request. | `specs/sandbox/spec.md` → *Requirement: Admin-only execution in v1*, scenario *Non-admin user blocked at API*.       |

The frontend's `enabled` predicate is convenience. The `/run`
endpoint MUST refuse non-admin requests independently of the UI.

### Layer 2 — The emulator

Each Run starts a fresh engine process tree inside the Ash Nazg
container. There is no engine container: an ExApp cannot start one (no
Docker CLI, no socket, no spawn API for ExApps — see
`openspec/changes/wire-dosbox-engine/design.md`, *Decision: the engine
ships in the host image*). The boundary at this layer is DOSBox-X: the
binary is a DOS program under emulation, never native code on the
container's CPU.

| Bound                       | Default                              | Backed by                                                                                 |
|-----------------------------|--------------------------------------|-------------------------------------------------------------------------------------------|
| Concurrent sessions         | 8                                    | `specs/sandbox/spec.md` → *Session resources are bounded by what the runtime offers*        |
| Scheduling priority         | nice +10 relative to the shim        | same requirement, scenario *A session cannot starve the shim*                              |
| Maximum session duration    | 4 h                                  | `specs/engines/spec.md` → *Engine session lifecycle bounded*                                |
| Idle window                 | 900 s without stream traffic         | same requirement; measured by the relay, the only place that sees it                        |
| Writable surface            | one private 0700 session directory   | `specs/sandbox/spec.md` → *A session writes only inside its own directory*                  |
| Termination                 | SIGTERM, 30 s grace, then SIGKILL    | `specs/engines/spec.md` → *Engine session lifecycle bounded*                                |

**What this layer does not give you**, stated because an earlier version
of this page promised it: there is no cgroup CPU or memory limit, the
root filesystem is not read-only, and the session runs under the same
uid as the shim. A compromise of DOSBox-X itself therefore reaches the
shim's environment, `APP_SECRET` included. The shim keeps its variables
out of the session's environment as hygiene, not as a boundary. Hard
resource isolation returns when each engine becomes its own ExApp, which
AppAPI deploys and the deploy daemon limits.

Idle termination is real since `streaming-proxy`: the stream passes
through the host's own relay, so "nobody is watching" is something it
observes rather than guesses. The clock resets on every frame in either
direction, and when it runs out the session ends the same way an
explicit close does — same path, same claim release.

### Layer 3 — The session sees one file

A session does not mount the user's Files. The shim downloads the single
binary being run into the session's private directory and starts the
emulator there.

| Claim                                                   | Backed by                                                                                   |
|---------------------------------------------------------|---------------------------------------------------------------------------------------------|
| A session can reach only the binary it was asked to run. | `specs/sandbox/spec.md` → *A session writes only inside its own directory*, scenario *The session sees one file* |
| The directory is removed when the session ends.          | same requirement, scenario *Session directory removed on close*                              |
| No mount privileges are needed at all.                   | There is no davfs2 mount; the download uses the shim's own WebDAV client.                     |
| Viewing credentials belong to one session.               | `specs/sandbox/spec.md` → *Session viewing credentials are per session*. Generated at spawn, written 0600 into the session directory, gone with it. The image carries no password. |
| Only the session's owner can watch it.                   | `specs/nextcloud-frontend/spec.md` → *A session stream is reachable only by its owner*. Checked before the upgrade; "not yours" and "does not exist" both answer 404. |

This is a narrower grant than the per-session WebDAV token the earlier
design described: the session never holds a credential, because it never
talks to Nextcloud.

## 3. Audit log per execution

Every dispatch — successful or refused — produces one entry in
Nextcloud's audit log. The schema:

```yaml
event:        ash_nazg.execution
user_id:      <admin user id>
file_path:    <Files-relative path of the binary>
file_sha256:  <hex digest>
engine:       <engine id, e.g. dosbox-x>
engine_image: <fully qualified OCI ref of the engine image used>
session_id:   <uuid v4>
started_at:   <iso8601>
ended_at:     <iso8601>
exit_status:  graceful_close | timeout | killed | refused
peak_memory_mb:  <int>
cpu_seconds:     <float>
detected_type:   <pe32 | mz-dos | elf | wasm | jar | unknown>
selected_engine: <engine id or null>
outcome:         dispatched | refused
reason:          <short reason on refusal, otherwise empty>
```

| Claim                                              | Backed by                                                                                            |
|----------------------------------------------------|------------------------------------------------------------------------------------------------------|
| Successful executions are audited.                 | `specs/sandbox/spec.md` → *Requirement: Audit log entry per execution*, scenario *Successful execution audit entry*. |
| Refused dispatches are also audited.               | `specs/sandbox/spec.md` → same requirement, scenario *Failed dispatch still audited*.                |
| Magic-byte detection refusals are audited.         | `specs/detection/spec.md` → audit-log requirement (every dispatch attempt).                          |

The audit entry is the **post-incident** primary source. Treat
log retention and shipping as part of the Nextcloud install's
existing audit posture; Ash Nazg writes to it, doesn't replace it.

## 4. Content distribution boundary

Ash Nazg's container images and git tree contain **zero**
proprietary content.

| Claim                                                                            | Backed by                                                                                  |
|----------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------|
| No proprietary OS images, ROMs, BIOS files, or proprietary fonts in the repo.    | `specs/sandbox/spec.md` → *Requirement: No bundled non-open-source content*.               |
| Engine images are similarly clean — no Microsoft Windows installation files etc. | Same requirement, scenario *Win 3.11 image not shipped*.                                    |
| User-supplied content boundary is documented.                                    | Same requirement, scenario *Documentation directs user to bring their own*; see also `docs/bring-your-own-content.md`. |

Verifying this claim on every release is the responsibility of the
Level-3 image-content audit (`docs/testing.md`). For the v1
release this is reviewed manually; the wiring change introduces a
scripted check that greps each layer for known proprietary
filename patterns.

## 5. What this does **not** protect against

Stating these explicitly is part of an honest threat model. None
of the items below are bugs — they are out of scope for v1 by
design.

- **A malicious admin.** Admin is trusted by design. An admin who
  uploads malware and runs it in Ash Nazg is exercising the system
  as intended; the sandbox protects everyone *else*. (See
  `SECURITY.md` § *Scope* — vulnerabilities requiring admin access
  are out of scope.)
- **A vulnerability in the engine binary itself** (DOSBox-X, Wine,
  …). The sandbox protects the host from the engine, not the
  engine from itself. Resource limits cap blast radius if an
  engine bug enables 100% CPU or OOM, but a remote-code-execution
  bug *inside* DOSBox-X reaching the binary's own privilege level
  is out of scope.
- **A Linux kernel sandbox escape.** If an attacker escapes the
  container's namespaces or seccomp filters via a kernel bug, every
  layer above is moot. Mitigation: keep the host kernel patched.
- **A bug in DOSBox-X itself.** Layer 2 is the emulator, so a
  vulnerability in DOSBox-X that lets an emulated program execute native
  code lands in the app container, under the app's uid, next to its
  Nextcloud credentials. Mitigation: keep the image current, and treat
  the engine as the boundary it is when deciding whether to enable the
  app at all.
- **Long-running side-channel attacks.** The 15-minute idle
  timeout limits the window for cache-timing or row-hammer style
  attacks but does not prevent them. Customers with this in their
  threat model should not enable Ash Nazg.
- **Data exfiltration via WebDAV write.** If an attacker has
  admin, they already have full Files access via every other
  Nextcloud surface. Ash Nazg does not introduce a new
  exfiltration path beyond what admin already has.
- **Multi-tenant isolation between admins.** v1 ships
  admin-only; multi-tenant scenarios with per-user Run privileges
  are explicitly future work (and would change much of this
  document).

## 6. Layered enforcement → verifier mapping

The promises above are checked at the corresponding verifier
layer; see `docs/testing.md` for the full layer system.

| Promise                                                                         | Layer that checks it          |
|---------------------------------------------------------------------------------|-------------------------------|
| Host shim refuses non-admin `/run`.                                              | Level 1 (pytest, in `wire-dosbox-engine`). |
| Session bounds: concurrency cap, private 0700 directory, priority, termination.   | Level 1 (pytest over the spawner) + Level 3 (a real Run on a real Nextcloud). |
| `<image-tag>` is concrete, never `latest`.                                       | Level 2 (`scripts/verify-info-xml.sh`). |
| Declared scopes are an AppAPI-recognised set.                                    | Level 2 + Level 3.            |
| Audit log entry contains every required field.                                   | Level 1 (pytest fixtures comparing against an expected schema). |
| Container image contains no proprietary binaries.                                | Level 3 (image-content audit). |

If any of those mappings ever has "by review only" instead of a
layer, that is a documentation bug. File it.

## 7. Reporting a vulnerability

See `SECURITY.md`. TL;DR: GitHub private security advisories,
90-day coordinated disclosure, in-scope = host shim, engine
containers, frontend, manifest. Out of scope = admin-required
attacks, upstream-tracked CVEs.

## 5. The stream, and what it does and does not open up

The screen reaches the browser through a relay in the app: AppAPI gives
an ExApp one port, and the sessions listen behind it, so nothing else
can bridge the two. Three things about that are worth an administrator's
attention.

**It rides the same door as everything else.** The stream is reached at
`/exapps/<appid>/…`, which the web server in front of Nextcloud routes to
the deploy daemon, and the daemon enforces the route's ADMIN level there
exactly as it does for the rest of the app. No port is published, and
nothing is exposed that Nextcloud does not gate. (The `app_api/proxy`
URL the rest of the app uses cannot carry a websocket at all: it is a
PHP controller and cannot return `101 Switching Protocols`.)

**The relay authorises before it forwards a byte.** Admin, as for
`/run`, and the session's owner. A session id is not a capability: ask
for someone else's session and the answer is the same 404 as for one
that does not exist, so the endpoint cannot be used to discover ids.

**What the relay does not do** is inspect the stream. It shuttles frames
and stamps an activity clock; it does not parse RFB, does not filter
what the emulator draws, and does not sit between the emulator and its
own credentials. If DOSBox-X is compromised, the relay is not what
stops the attacker — that remains the emulator boundary described in
Layer 2.

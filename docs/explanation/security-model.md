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
input to the sandbox. Everything else — the host shim, the engine
container image, the Nextcloud admin who installed the app — is in
the trusted base. The system protects the rest of the Nextcloud
instance and the Internet at large from the user-supplied binary.
It does **not** protect the Nextcloud instance from a malicious
admin (admin is trusted by design, in v1).

## 2. The three sandbox layers

Defence in depth, three independent layers. A bypass of any one
layer should not by itself yield arbitrary code execution outside
its intended scope.

### Layer 1 — Nextcloud admin gating

Only admin users can dispatch a binary in v1.

| Claim                                              | Backed by                                                                                                              |
|----------------------------------------------------|------------------------------------------------------------------------------------------------------------------------|
| The Files action is hidden from non-admins.         | UX hide; **not** security. See spec, "Admin-only execution in v1" — frontend hide is documented as UX, not enforcement. |
| The host shim re-validates admin status on every Run request. | `specs/sandbox/spec.md` → *Requirement: Admin-only execution in v1*, scenario *Non-admin user blocked at API*.       |

The frontend's `enabled` predicate is convenience. The `/run`
endpoint MUST refuse non-admin requests independently of the UI.

### Layer 2 — Container resource limits

Each Run produces a fresh ephemeral engine container. The host
imposes hard limits via Docker run flags before the binary
executes.

| Limit                          | Default       | Backed by                                                                                          |
|--------------------------------|---------------|----------------------------------------------------------------------------------------------------|
| CPU                            | 1.0 core      | `specs/sandbox/spec.md` → *Resource limits enforced at container level*, scenario *CPU limit enforced* |
| Memory                         | 1024 MB       | `specs/sandbox/spec.md` → same requirement, scenario *Memory limit enforced*                        |
| Network                        | none — only the AppAPI proxy network | `specs/sandbox/spec.md` → same requirement, scenario *No host network exposed*    |
| Root filesystem                | read-only     | `specs/sandbox/spec.md` → *Requirement: Read-only root filesystem*                                  |
| Writable scratch               | tmpfs at `/tmp`, 256 MB | Design note in `design.md` § *Security posture*; codified per-engine via `SessionConfig`. |
| Idle timeout                   | 900 s (15 min, configurable) | `engines/spec.md` → dosbox-x `SessionConfig.idle_timeout_seconds`                       |
| Termination on idle/timeout    | SIGTERM, 30 s grace, then SIGKILL | Design note in `design.md` § *Security posture*.                                   |

Memory and CPU enforcement is via cgroups, not application-layer
self-policing. The engine binary cannot lift its own ceiling.

### Layer 3 — Per-session WebDAV scope-restricted token

Each spawned engine receives a per-session AppAPI user token. The
WebDAV mount inside the container uses that token; the token's
scope is the user's own Files, nothing else.

| Claim                                                  | Backed by                                                                                                       |
|--------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------|
| Token can read/write only the issuing user's Files.    | `specs/sandbox/spec.md` → *Requirement: Per-session token scoping*, scenario *Token cannot read other users' files*. |
| Token expires when the session ends.                   | `specs/sandbox/spec.md` → same requirement, scenario *Token expires with session*.                              |
| Token is never exposed to the binary directly.         | The token is consumed by `davfs2` at mount time; it is not an environment variable visible to the running binary's process.  Implementation in `wire-dosbox-engine`. |

A binary that escapes the davfs2 mount (which would be a Linux
kernel bug) still gains nothing — the token is gone from process
memory once the mount is active, and the network is locked down at
Layer 2.

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
- **A Linux kernel sandbox escape.** If an attacker escapes
  cgroups, namespaces, or seccomp filters via a kernel bug, every
  layer above is moot. Mitigation: keep the host kernel patched.
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
| Engine spawn config enforces CPU / memory / network / read-only root.            | Level 1 (pytest over `SessionConfig`) + Level 3 (real Docker spawn). |
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

# Security Policy

## Reporting a vulnerability

Please report security issues **privately**, never via a public GitHub
issue or pull request.

Preferred channel: open a private security advisory on GitHub at
<https://github.com/MWest2020/ash-nazg/security/advisories/new>.

Alternative: email the maintainer at the address listed on the GitHub
profile of [@MWest2020](https://github.com/MWest2020). PGP key on
request.

When reporting, please include:

- A description of the issue and the attack scenario it enables.
- The affected component (host shim, engine container, frontend,
  AppAPI integration, deployment manifest).
- The Ash Nazg version (commit SHA or tag) and the Nextcloud +
  AppAPI versions on which it was reproduced.
- A proof of concept, if you have one, or steps to reproduce.

## Disclosure policy

- We aim to acknowledge reports within **5 business days**.
- We aim to ship a fix or mitigation within **90 days** of
  acknowledgement. Under-90-day disclosure is preferred when a fix
  ships sooner.
- Coordinated disclosure: we will agree a release date with you
  before publication. We will credit reporters who wish to be credited.
- High-severity issues affecting users in production may warrant a
  faster timeline; we will discuss case-by-case.

## Scope

In-scope:

- The Ash Nazg host container (`host/`) and its HTTP surface.
- The Ash Nazg engine containers (`engines/*/`) including their
  startup configuration and sandbox posture.
- The frontend (`frontend/`) for any client-side issue (XSS, CSRF,
  iframe-sandbox bypass).
- The Nextcloud app manifest (`appinfo/info.xml`) and AppAPI
  registration handshake.

Out-of-scope:

- Vulnerabilities in upstream dependencies that are already publicly
  tracked — please report those upstream and link the CVE here.
- Vulnerabilities that require attacker-controlled administrator
  access on the Nextcloud instance (admin is trusted by design).
- Findings in user-supplied binaries executed inside an engine; that
  is the user's responsibility, not the project's. The threat model
  treats user binaries as untrusted **input** to the sandbox, never
  as part of the trusted base.

## Security model summary

See `docs/security-model.md` for the full design. Highlights:

- Each Run produces a fresh ephemeral engine container with hard CPU,
  memory, and wall-clock limits, no host network, and a per-session
  WebDAV mount restricted to the user's own Files.
- The host shim runs as non-root in its container. Engine containers
  run as non-root inside the engine namespace.
- The `appinfo/info.xml` declares only the scopes the project needs:
  `FILES`, `AUDIT_LOGS`, `NOTIFICATIONS`. AI provider scopes are
  **not** requested.

## Hall of fame

Reporters who responsibly disclose a confirmed issue will be listed
here (with permission) once the first such report is fixed.

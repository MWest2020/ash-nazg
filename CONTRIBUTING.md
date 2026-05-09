# Contributing to Ash Nazg

Thank you for considering a contribution. Ash Nazg follows a strict
**spec-driven development** workflow using [OpenSpec](https://github.com/Fission-AI/OpenSpec).
Every change starts with a written proposal, and every proposal must
pass `openspec validate` before code review.

## TL;DR

1. **Open a change proposal first.** No code-only PRs.
2. **Write the spec, then the code.** Specs live under
   `openspec/changes/<change-id>/specs/`.
3. **Validate locally:** `openspec validate <change-id>` must pass.
4. **One change per PR.** PRs that touch multiple OpenSpec change
   folders will be asked to split.
5. **Conventional commits**, AGPL-3.0-or-later sign-off.

## The OpenSpec workflow

```
idea  →  /opsx:propose <name>  →  proposal.md + design.md +
                                  tasks.md + specs/*/spec.md
                              ↓
                          openspec validate
                              ↓
                          implementation
                              ↓
                          /opsx:archive <name>
                              ↓
                  specs merge into openspec/specs/
```

### When to open a proposal

You **must** open one for:

- Any new feature or runtime engine.
- Any change to the AppAPI handshake, scopes, or deployment manifest.
- Any change to the security posture (sandbox limits, network
  policy, audit format, scope set).
- Any change to public-facing UX (Files actions, admin settings,
  notifications surface).

You **may** skip the proposal for:

- Documentation typo fixes.
- Lockfile-only updates that don't change behavior.
- Test-only additions that strengthen existing requirements without
  introducing new ones.

If unsure: open a proposal. The cost is low.

### Drafting a proposal

```bash
# Inside Claude Code with the opsx skill installed:
/opsx:propose my-change-name

# Or by hand:
mkdir -p openspec/changes/my-change-name/specs
$EDITOR openspec/changes/my-change-name/proposal.md
$EDITOR openspec/changes/my-change-name/design.md
$EDITOR openspec/changes/my-change-name/tasks.md
```

A proposal must include:

- `proposal.md` — Why, What changes, Impact.
- `design.md` — architecture decisions, trade-offs, security posture.
- `tasks.md` — actionable checklist; reviewer marks progress here.
- `specs/<capability>/spec.md` — normative requirements with at least
  one `#### Scenario:` block per `### Requirement:`. Each requirement
  body MUST contain `SHALL` or `MUST` on its **first line** — the
  validator only inspects the first physical line for the keyword.

Run `openspec validate <change-id>` until it reports `is valid`.

### Implementing a proposal

- Tick boxes in `tasks.md` as you complete them.
- Open a PR titled `<change-id>: <short summary>`.
- The PR body should link the proposal and call out any deviations.
- CI runs `openspec validate` against any change folder touched in
  the PR.

### Archiving

Once tasks are done and merged, run:

```bash
/opsx:archive <change-id>
# or:
openspec archive <change-id>
```

This moves the spec deltas into `openspec/specs/` (the canonical
spec tree) and stamps the change as completed.

## Code style

- **Python (host):** ruff + black via `pyproject.toml`. 4-space
  indent. Type hints required on all public functions. Pydantic
  v2 models for any cross-boundary data.
- **TypeScript / Vue (frontend):** ESLint + Prettier. 2-space
  indent. `@nextcloud/eslint-config` is the base.
- **Shell (engine entrypoints):** `set -euo pipefail` at the top,
  shellcheck-clean.
- **Dockerfiles:** non-root final user, multi-stage builds, pinned
  base images by digest in production builds.

## Commits

Conventional Commits format:

```
<type>(<scope>): <subject>

<body>

Refs: openspec/changes/<change-id>
```

Types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `ci`,
`build`, `perf`, `revert`.

Co-author tags from AI-pair-programming sessions are welcome and
encouraged for transparency.

## License & sign-off

By contributing you agree your contribution is licensed under
**AGPL-3.0-or-later**, the same license as the project. We do not
require a CLA. Sign your commits with `git commit -s` so each commit
carries a `Signed-off-by:` line per the
[Developer Certificate of Origin](https://developercertificate.org/).

## Code of Conduct

Be kind. Disagree on technical merits. Critique the work, not the
person. The maintainer reserves the right to ask anyone making this
project unwelcoming to step away.

## Where to ask questions

- General design: open a GitHub Discussion.
- Specific bugs: open a GitHub Issue.
- Security: see `SECURITY.md` — never on public channels.

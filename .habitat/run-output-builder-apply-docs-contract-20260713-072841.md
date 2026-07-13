# Habitat builder — apply-docs-contract

_run_id builder-apply-docs-contract-20260713-072841 · verdict ok · 2026-07-13T07:31:31Z_

---

The change is complete. Here's the run report.

## Run report — `apply-docs-contract` (builder)

**Branch:** `habitat/builder/apply-docs-contract` (worked in place; no branch created — per task 1.1 the harness pushes).

### What I did

Applied the handbook docs contract to `docs/`:

**Migrated (via `git mv`, history preserved) + added front matter** — all `status: draft`, `last_reviewed: 2026-07-13` (migration date, no content review performed):
- `installation.md`, `demo.md`, `bring-your-own-content.md`, `user-guide.md` → `docs/how-to/`
- `security-model.md`, `testing.md` → `docs/explanation/`

**Stubs left at old paths** (external links exist — README, SECURITY.md, THIRD_PARTY_NOTICES.md, engine README, CHANGELOG all reference `docs/*.md`), each `status: deprecated` with a pointer to the new location.

**New:** `docs/index.md` (`status: current`) — one-paragraph project summary, status, link to README, links to the `how-to/` and `explanation/` sections.

**`.mcp.json`:** already present at root as the seed template with `url: "TODO-change-3"` placeholder intact — left unchanged (task 2.4 satisfied).

### Self-check (task 3.1) ✅
- Markdown only in allowed places: `how-to/`, `explanation/`, plus root `index.md` + stubs. Empty `reference/` omitted per contract.
- Front matter on all 13 pages (verified).
- One language (English); README kept, index links to it rather than replacing.
- Internal cross-ref in `how-to/user-guide.md` → `./bring-your-own-content.md` still resolves (both moved to `how-to/`).
- License untouched (AGPL-3.0, deliberate).

### Tasks
1.1, 2.1, 2.2, 2.3, 2.4, 3.1 → checked off. **4.1 (open PR) left unchecked** — opening the PR needs a push, which the harness owns (task 1.1) and the builder role forbids me doing on my own. Changes are staged in the working tree, ready for the harness to commit/push. **I did not merge.**

### Ready PR
**Title:** `docs: apply handbook docs contract`

**Body:**
> Applies the Westmarch handbook docs contract to `ash-nazg` (wave 2).
>
> - [x] `docs/` restructured into `how-to/` + `explanation/`; contract subfolders only carry markdown
> - [x] 6 existing docs migrated (git mv, history kept); stubs left at old paths for external links
> - [x] Front matter on every page: migrated-without-review → `status: draft`, `last_reviewed: 2026-07-13`; no `owner` field
> - [x] `docs/index.md` added (what/status/README link/section links)
> - [x] `.mcp.json` present with `TODO-change-3` placeholder (change-3 fills the handbook URL)
> - [x] English only; README kept, not replaced; AGPL-3.0 license unchanged (deliberate)
> - No merge — Mark merges.

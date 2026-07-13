# Habitat reviewer — apply-docs-contract

_run_id reviewer-apply-docs-contract-20260713-073136 · verdict ok · 2026-07-13T07:33:55Z_

---

Review complete. I've verified the builder's diff against the reviewer contract, the proposal, and the tasks. Here is my verdict.

---

# Reviewer verdict: **PASS**

Change `apply-docs-contract` · branch `habitat/reviewer/apply-docs-contract` · builder commit `bb227a3`. No CLAUDE.md exists in this repo, so I judged against the change proposal + the reviewer contract only. Read-only review — no files changed.

## 1. Scope — PASS
- Diff = docs migration (6 pages moved, 6 stubs, `index.md`), `tasks.md` checkboxes, and harness bookkeeping (`.habitat/*`, `run-report.json`).
- Repo-specific mapping followed exactly: `installation`, `demo`, `bring-your-own-content`, `user-guide` → `how-to/`; `security-model`, `testing` → `explanation/`.
- Migrated bodies are **byte-identical** to the originals in `main` (only a leading blank line added after front matter). No content drift.
- `.mcp.json` (task 2.4) is present with placeholder `TODO-change-3` — it landed in the seed commit, so it's correctly absent from this diff; end-state satisfies the contract.
- `run-report.json` / `.habitat/*` are harness-generated audit artifacts, not builder content edits — not a scope violation.
- Task 4.1 (open PR) correctly left unchecked — that's for after review; Mark merges.

## 2. Contract (Diátaxis-light) — PASS
- All 13 markdown pages carry front matter with `status` + `last_reviewed: 2026-07-13`; every `status` is a valid enum value.
- **No `owner` field** anywhere (the one `grep` hit is the word "ownership" in prose).
- Statuses correct per contract: migrated pages = `draft`, redirect stubs = `deprecated`, new `index.md` = `current`.
- One language throughout (English).
- `index.md` links to `../README.md` (exists) and to the present sections; boilerplate ≤ 3 lines. ✅
- Flat-root stubs (`docs/*.md`) *are* markdown outside `how-to/`/`explanation/`, which brushes against the "only these dirs carry markdown" line — but the proposal **explicitly mandates** leaving redirect stubs at old locations, and they're `status: deprecated` pointer pages (an aggregator filtering by status skips them). Reconciled: they're contract-sanctioned migration artifacts, not content pages.

## 3. Cage — PASS
`CLAUDE.md`, `.claude/agents/`, and CI config: **untouched**.

## 4. Secrets — PASS
Secret-pattern scan hits are all security-model *prose* about per-session WebDAV tokens (architectural description). No real tokens, credentials, keys, or secret URLs.

## One note for Mark (non-blocking)
The proposal says *"Minimum viable: `index.md` + één reference-pagina"*, but there is **no `reference/` page** — all 6 existing docs are genuinely how-to/explanation material, and the proposal also says *"lege mappen weglaten"* (omit empty folders). Fabricating a reference page with no real reference content would be worse. I read the "one reference page" line as a general floor subordinate to the repo-specific mapping, so this is **not** a fail — flagging it only so you can confirm that interpretation on merge.

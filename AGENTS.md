# TraceQ: Universal Agent Protocol

Universal protocol for all coding agents (Antigravity, Claude Code). Public-repo safe (no local paths, private names, or secrets).

## 1. Hard Boundaries (Never Violate)
- **Held-out isolation:** NEVER open, read, or grep `world/tp202*`, `world/pw001*`, `answer_key/TP-202`, `answer_key/PW-001`, or held-out docs/recordings/matrix rows. Run held-out commands ONLY via `bash scripts/heldout_run.sh <TAG> -- <cmd>` and report only scorer outputs (`gate`, `item id`, expected/got, counts). Never re-run a failed held-out gate until fixed on dev (`TP-201`).
- **Git & branch safety:** NEVER push to `main`, force-push, or pass `--no-verify`. Push only prefixed branches (`feat/`, `fix/`, `docs/`, `chore/`, `test/`, `refactor/`). Code reaches `main` only via owner-merged PRs (agents may merge `docs/*`/`chore/*` PRs or ticket PRs into an integration branch after green CI).
- **Secrets & public repo (ADR 0001):** NEVER read/commit `.env` or `.denylist.local`, or leak private/plant/vendor names (`scripts/check_denylist.py`, `denylist-text.yml`; copy `.denylist.local` into new worktrees).
- **Circuit breaker & integrity:** After 3 failed fixes on the same error, STOP and report root cause + options. Never weaken tests, loosen tolerances, or add unapproved suppressions (`tests/test_boundaries.py`). Cite only observed outputs after final edit.

## 2. Single Source of Truth (SSOT)
- **Work & order:** GitHub Issues in `gedeyandi123/traceq` (`docs/agents/issue-tracker.md`, `docs/agents/triage-labels.md`). Do NOT create `STATUS.md`, `tasks/plan.md`, or `BACKLOG.md`.
- **Domain & decisions:** `GLOSSARY.md` (`docs/agents/domain.md`), `docs/adr/`, `docs/design/synthetic-dataset.md`, `docs/demo-runbook.md`.
- **Architecture & UI:**
  - **ADR 0008:** Layered modular monolith (`lint-imports --no-cache`, `pyright` strict on `src/traceq/`). System never imports `traceq_dataset`/`traceq_eval`; scorer never loads `assembly`/`proposals`/`db`. Ports only for two real implementations.
  - **ADR 0014 (supersedes ADR 0011):** Tailwind CSS v4 (`@theme` + `--color-*: initial` in `web/src/app/globals.css`), owned `radix-ui` primitives (`web/src/components/ui/`), `lucide-react`, bundled `@fontsource-variable/inter`, light-only, 100% self-hosted/offline, semantic colour-literal guard (`web/src/colour-literals.test.ts`), and `docs/DESIGN.md` as visual/UX SSOT. Do NOT add font/asset CDNs, dark mode, or unapproved suppressions (`tests/test_boundaries.py`).

## 3. Verification Loop
- **Primary local pre-PR gate:** `powershell -ExecutionPolicy Bypass -File scripts/verify.ps1 -Mode fast -Scope <all|python|web>` (supports `-TestPath <paths>`, `-DbPath <paths>`, `-Build`). Locally run `-Mode fast -Scope <affected>` + targeted `-DbPath`; rely on parallel CI (`hygiene`, `py-fast`, `py-db`, `py-slow`, `web`) for full DB/slow suites unless editing `src/traceq/db/`, migrations, or `tests/conftest.py`. When `web/` changes, also run `-Build` (+ affected `docs/demo-runbook.md` cases).
- **Windows / Sandbox rules:** PowerShell 5.1 uses `;` + `$LASTEXITCODE` (never `&&`). Run `TestClient`/`anyio` (`socketpair`) DB/API tests and `gh` CLI with `BypassSandbox: true` when the sandbox blocks local sockets or network.
- **Memory (16 GB host):** Avoid concurrent heavy runs (`pytest` ~1.5 GB, `next build` ~1.4 GB, `vitest` ~1.0 GB); stop check servers right after verification.

## 4. Feature Flow & Eval Loop
- **Feature flow:** `grilling` + `domain-modeling` → fresh-context doubt review → spec + owner approval → issues with native blocking edges → `tdd` on isolated branches/worktrees → code review + owner merge to `main`.
- **Autonomous `ready-for-agent` Done:** For issues labelled `ready-for-agent`, complete end-to-end without plan-review handbacks (unless an ADR conflict arises): implement with TDD → verify → commit → push → `gh pr create` → check CI green (auto-fix if red).
- **Multi-PR epics & slice discipline:** Use an integration branch (`feat/<epic>`) per §1 and split large epics into **3–4 cohesive slices** (~1,500–3,000 non-generated LOC/PR) or **1–2 slices** for *Thin* epics (Step 6–7 per ADR 0010); consolidate OpenAPI/TS client regen per backend slice. Run **1 fresh subagent per slice sequentially** with a **Shared Epic Brief (<80 lines)** (endpoints, schemas, target files, ADR invariants) so subagents skip re-reading full docs. On `429`/interruption, **Resume Protocol**: the replacement subagent starts from `git status`, `git diff --stat`, and test state on the existing branch.
- **Epic Pre-PR & Post-Merge Hygiene:** Ticket PRs into `feat/<epic>` use `Part of #<spec>, ticket #<n>`. Before opening the final integration PR to `main`, sync `docs/DESIGN.md` & `docs/demo-runbook.md` on `feat/<epic>`, run 1 visual checkpoint (`390px`/`1366px`/`1440px`) for UI epics, and list `Closes #<n>` **one per line** for the spec and all child tickets in the PR body. After owner merge: `git fetch --prune`, delete merged local/remote branches (`git branch -D`), `git worktree prune`, and verify `gh issue list --label ready-for-agent`.
- **Eval loop:** Prompt/model changes are experiments (Batch API within budget, `traceq_eval`, PR updating `baselines/*.json` + run link, replay tolerance 0). Report `k/n` split by dev (`TP-201`) vs held-out and log cost. Answer-key changes go in their own PR.
- **Owner-only:** Grilling answers, spec approval, merging code to `main`, gates, scoring rules/claims, ADRs, spend, external comms.

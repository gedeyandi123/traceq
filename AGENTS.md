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
  - **ADR 0008:** Layered modular monolith (`uv run lint-imports`, `pyright` strict on `src/traceq/`). System never imports `traceq_dataset`/`traceq_eval`; scorer never loads `assembly`/`proposals`/`db`. Ports only for two real implementations.
  - **ADR 0014 (supersedes ADR 0011):** Tailwind CSS v4 (`@theme` + `--color-*: initial` in `web/src/app/globals.css`), owned `radix-ui` primitives (`web/src/components/ui/`), `lucide-react`, bundled `@fontsource-variable/inter`, light-only, 100% self-hosted/offline, semantic colour-literal guard (`web/src/colour-literals.test.ts`), and `docs/DESIGN.md` as visual/UX SSOT. Do NOT add font/asset CDNs, dark mode, or unapproved suppressions (`tests/test_boundaries.py`).

## 3. Verification Loop
- **Primary local pre-PR gate:** `powershell -ExecutionPolicy Bypass -File scripts/verify.ps1 -Mode fast` (runs `ruff`, `pyright`, `lint-imports`, `pytest -m "not slow and not db"`, `next typegen`, `typecheck`, `lint`, `vitest`; optional `-TestPath <path>` for targeted tests). When `web/` changes, also run `npm run build` in `web/` (+ affected `docs/demo-runbook.md` cases).
- **Full suite:** Parallel CI (`py-fast`, `py-db`, `py-slow`, `web`) runs all DB and slow OCR/Docling/render tests; run `-Mode full` locally only when changing slow/pipeline code.
- **Memory (16 GB host):** Avoid concurrent heavy runs (`pytest` ~1.5 GB, `next build` ~1.4 GB, `vitest` ~1.0 GB); stop check servers right after verification.

## 4. Feature Flow & Eval Loop
- **Feature flow:** `grilling` + `domain-modeling` → fresh-context doubt review → spec + owner approval → issues with native blocking edges → `tdd` on isolated branches/worktrees → code review + owner merge to `main`.
- **Autonomous `ready-for-agent` Done:** For issues labelled `ready-for-agent`, complete end-to-end without pausing to ask: implement with TDD → verify → commit → push → `gh pr create` (`Closes #<n>`) → check CI green (auto-fix if red).
- **Multi-PR epics:** Use an integration branch (`feat/<epic>`) per §1 and run **1 fresh subagent per ticket PR sequentially** (keeping context clean, token cost linear, and 16 GB RAM safe with zero human touchpoints between tickets); merge each ticket PR into `feat/<epic>` after green CI, run 1 visual checkpoint (`390px`/`1366px`/`1440px`) for UI epics, then open 1 final PR to `main` for owner merge.
- **Session & token discipline:** Bound single-agent sessions to **1–2 ticket PRs** (or use 1 fresh subagent per PR / compact between PRs) to prevent context bloat and quality drift; use sequential Plan→Execute for dependent slices on the 16 GB host (reserve multi-agent fan-out for independent tasks); run `scripts/verify.ps1 -Mode fast` (with `-TestPath` when targeted) locally and rely on parallel CI for DB/slow suites.
- **Eval loop:** Prompt/model changes are experiments (Batch API within budget, `traceq_eval`, PR updating `baselines/*.json` + run link, replay tolerance 0). Report `k/n` split by dev (`TP-201`) vs held-out and log cost. Answer-key changes go in their own PR.
- **Owner-only:** Grilling answers, spec approval, merging code to `main`, gates, scoring rules/claims, ADRs, spend, external comms.

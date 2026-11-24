# TraceQ Antigravity Workspace Guards

These workspace rules mirror TraceQ's local Claude Code hooks (which do not execute in Antigravity). Always obey them:

1. **Held-Out Isolation (CRITICAL):** NEVER open, read, or search `world/tp202*`, `world/pw001*`, `answer_key/TP-202`, `answer_key/PW-001`, or any held-out document, recording, or matrix row. Run held-out commands ONLY through `bash scripts/heldout_run.sh <TAG> -- <command...>` and report only scorer summary outputs.
2. **Git & Branch Safety:** NEVER push to `main`, force-push, or use `--no-verify`. Never merge code PRs into `main` (owner-only).
3. **Secrets & Public Repo:** NEVER read or commit `.env` or `.denylist.local`, and never write private names, real vendor names, or machine-local paths into any tracked file.
4. **SSOT & Architecture Integrity:** Follow `AGENTS.md`, `GLOSSARY.md`, `docs/adr/0008-modular-monolith-pragmatic-ports.md`, and `docs/adr/0011-web-styling-css-modules-over-tokens.md`. Do NOT create `STATUS.md`, `tasks/plan.md`, `BACKLOG.md`, or `docs/DESIGN.md`, and do NOT introduce Tailwind or external UI kits.

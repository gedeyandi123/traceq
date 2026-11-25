# TraceQ Antigravity Workspace Guards

Follow `AGENTS.md` as the universal protocol (SSOT, ADRs, verification).
Claude Code hooks (`.claude/hooks/*.mjs`, `~/.claude/hooks/*`) do **not** execute in Antigravity, so self-enforce:
- Held-out isolation: never open/read/grep `world/tp202*`, `world/pw001*`, `answer_key/TP-202`, `answer_key/PW-001`; run held-out only via `bash scripts/heldout_run.sh <TAG> -- <cmd>`.
- Git & secrets: never push to `main`, force-push, use `--no-verify`, merge code PRs into `main`, or read/commit `.env` or `.denylist.local`.
- Windows verification & CLI: run `scripts/verify.ps1 -Scope python` (including `py-fast` `TestClient`/`anyio` tests and DB tests), `git` write operations, and `gh` CLI with `BypassSandbox: true` (`scripts/verify.ps1` enforces a 2s `socketpair()` preflight).

# Porting the protocol to another coding agent

The universal protocol already lives in `AGENTS.md`, and `CLAUDE.md` imports `@AGENTS.md`. Use this checklist when onboarding an additional coding agent harness onto TraceQ.

## What carries over and what does not

| Layer | Carries over? | Why |
|---|---|---|
| Branch protection on `main` (PR, `checks`, admins included) | Yes | Enforced by GitHub |
| CI: gitleaks, denylist, pyright, pytest, `tests/test_isolation.py`, `denylist-text` | Yes | Runs on GitHub |
| pre-commit hooks (ruff, gitleaks, denylist) | Partly | Git runs them for any agent, unless the agent commits with `--no-verify` |
| Design doc, ADRs, GLOSSARY, scorer, `docs/agents/*` | Yes | Plain files |
| `AGENTS.md` / `CLAUDE.md` | Yes | Universal rules live in `AGENTS.md`; `CLAUDE.md` only adds Claude Code model/hook notes |
| mattpocock-skills | Check per tool | Plain `SKILL.md` files; support and invocation differ by harness |
| `.claude/agents/`, `.claude/hooks/readonly-bash.mjs` | No | Claude Code formats |
| The owner's local guards (push/merge/admin `gh` guard, `.env` block, permission deny rules) | No | Live in the owner's Claude Code settings |
| The agent's memory | No | Stored by Claude Code outside the repo |

## Checklist on the day of the switch

1. **Instructions.** Move the body of `CLAUDE.md` to `AGENTS.md` and leave `CLAUDE.md` with one line, `@AGENTS.md`. Keep the Claude-specific Models section in `CLAUDE.md` under a "Claude Code" heading, or mark it as such in `AGENTS.md`.
2. **Local guards.** Rebuild them with the new agent's hook or permission mechanism, and test them with the same cases as the Claude Code guard tests:
   - no push to `main` or `master` in any form (`HEAD:main`, a bare push on `main`), and no force push;
   - no `--no-verify`;
   - no `gh pr merge` except `docs/*` and `chore/*` into `main` and ticket PRs into an integration branch;
   - no `gh repo edit/delete`, no `gh secret` writes, and no `gh api` writes to settings, protection or secrets;
   - no reading `.env` files or credential stores.
3. **Repositories without server-side protection.** A private repo on a free plan has no branch protection, so the local guards are its only defence. Give the new agent a GitHub token scoped to what it needs, or no access to such repos at all.
4. **Data.** ADR 0001 still holds: no private document or name goes to any LLM. Decide which vendor may read anything outside this public repo before granting access, and check that vendor's data-retention terms.
5. **Context.** The plan is already in GitHub issues and the decisions in the repo (`AGENTS.md`, §2 Single Source of Truth). Move what only the agent's memory holds (owner preferences, machine-local setup) into a place the new agent reads. Private items never go into this public repo.
6. **One agent at a time.** Two agents working the same repo collide on branches and worktrees.
7. **Verify.** Run one docs ticket end to end with the new agent (branch, checks, PR, merge rules) before giving it a code ticket.

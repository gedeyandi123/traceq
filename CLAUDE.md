@AGENTS.md

## Claude Code

This section applies only when running in Claude Code. Universal protocol, SSOT, boundaries, and verification rules live in `AGENTS.md`.

### Effort & Models

The session runs Opus 5.5 at effort `medium` (its default) for grilling, spec and merging. Subagents are spawned by name (`subagent_type`) from `.claude/agents/`, which fixes their model, effort and tools:

| Agent | Use for | Model / effort | Tools |
|---|---|---|---|
| `implementer` | One ticket. Pass `model: sonnet` for a mechanical ticket (docs, renames, config, boilerplate) and `effort: high` for scoring rules and gates | inherit (Opus) / `medium` | edit, own worktree |
| `reviewer` | Both code-review axes and the plan doubt review | inherit (Opus) / `medium` | read-only |
| `explorer` | A lookup: where is X, which files mention Y | Haiku / `low`, no CLAUDE.md | Read, Glob, Grep |

The session's own effort changes only by the owner typing `/effort`. Say "switch to `/effort high`" before a decision on gates, scoring rules or ADRs, or after two failed attempts at the same bug, and "back to `/effort medium`" when done. `xhigh` and `max` are not used routinely. If Sonnet tickets keep failing CI or need rework, move that kind of ticket back to Opus.

### `implement-spec` Subagent Mapping

- **Exploration subagent (step 2):** `explorer` for codebase lookups (save notes in session scratchpad, never in the repo). External docs go through `research` or `claude-api` in the main session.
- **Implementer subagents (step 4):** `implementer`, **one at a time sequentially** (one fresh subagent per slice; respect 16 GB RAM limit in `AGENTS.md`). Delegation message holds only pointers: ticket number, spec issue, integration branch, and commit co-author line.
- **Merger subagent (step 5):** none. Main session merges ticket PRs into the integration branch (`gh pr merge <n> --squash`) without prematurely closing tickets; the final integration PR into `main` closes the spec and all child tickets via `Closes #<n>` one per line.
- **Integration PR (steps 3 and 8):** draft PR into `main` closing the spec issue, listing every ticket; owner merges it.
- **Standalone / ticket chain:** standalone uses `<prefix>/<n>-<slug>` into `main`; dependent tickets share `feat/<topic>` or `fix/<topic>`.
- **Cleanup (step 9):** `git worktree prune` and delete leftover `worktree-agent-*` and ticket branches.

### Hook & Skill Notes

- `.claude/hooks/heldout-bash.mjs` and `.claude/hooks/readonly-bash.mjs` guard Bash/PowerShell in Claude Code (tests: `node .claude/hooks/readonly-bash.test.mjs` and `node .claude/hooks/heldout-bash.test.mjs`).
- Main session reads `path:line` cited by `explorer` before relying on it; never use the general-purpose agent for these roles.
- User-only Matt skills (`to-spec`, `to-tickets`, `implement-spec`, `retro`, `setup`) run by reading their `SKILL.md` from `mattpocock-skills` when asked in prose. `retro` runs per milestone, not per PR.
- Long-lived demo/eval servers are started by the main session in their own console windows (`Start-Process`), not as background shells.

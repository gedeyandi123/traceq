# TraceQ: agent protocol

Domain language: `GLOSSARY.md`. Decisions: `docs/adr/`. Dataset and eval design: `docs/design/synthetic-dataset.md`. Commands: `README.md`.

Checks before claiming done (show the output): `pre-commit run --all-files`, `uv run pyright`, `uv run pytest -q`.

## Agent skills

### Issue tracker

GitHub Issues in `gedeyandi123/traceq` (public). See `docs/agents/issue-tracker.md`.

### Triage labels

The five default labels (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `GLOSSARY.md` and `docs/adr/` at the root. See `docs/agents/domain.md`.

## Flow per feature

1. `grilling` + `domain-modeling`: decisions land in `GLOSSARY.md` and `docs/adr/`. Prototype only when code must answer a question; at most two rounds on paper, then a probe.
2. A fresh-context subagent reviews the plan for doubts (strongest counter-argument per decision).
3. to-spec, then the owner approves it, then to-tickets (issues with native blocking edges). Keep user stories to what the slice needs.
4. implement-spec: integration branch `feat/<spec>`; each ticket in its own worktree, built by a fresh subagent with `tdd`. Ticket PRs target the integration branch and the agent merges them after CI; `code-review` runs on the integration branch; one PR to `main`, merged by the owner.
5. `retro` per milestone, not per PR. No separate protocol audits.

The user-only Matt skills (to-spec, to-tickets, implement-spec, retro, setup) run by reading their `SKILL.md` from the installed `mattpocock-skills` plugin when the owner asks in prose.

## Eval loop (prompts and models)

A prompt or model change is an experiment, not a ticket: change it, run live (Batch API), score with `traceq_eval`, and open a PR that updates `baselines/<Equipment>.json` and links the run. CI replays recorded outputs at tolerance 0. Report rates with k/n and the split (dev TP-201 vs held-out). Log the cost of each live run. API calls only within the prepaid budget.

## Models

The session runs Opus 5.5 at effort `medium` (its default) for grilling, spec and merging. Subagents are spawned by name (`subagent_type`) from `.claude/agents/`, which fixes their model, effort and tools:

| Agent | Use for | Model / effort | Tools |
|---|---|---|---|
| `implementer` | A ticket with eval, scorer, pipeline, prompt or domain logic | inherit (Opus) / `medium`; pass `effort: high` for scoring rules and gates | edit, own worktree |
| `implementer-light` | A mechanical ticket (docs, renames, config, boilerplate) | Sonnet / `medium` | edit, own worktree |
| `reviewer` | Both code-review axes and the plan doubt review | inherit (Opus) / `medium` | read-only |
| `explorer` | A lookup: where is X, which files mention Y | Haiku / `low`, no CLAUDE.md | Read, Glob, Grep |

How implement-spec's roles map here:

- **Exploration subagent (step 2):** `explorer` for codebase lookups. It cannot write, so the main session saves its notes in the session scratchpad, never in the repo. External docs go through the `research` or `claude-api` skill in the main session.
- **Implementer subagents (step 4):** `implementer` or `implementer-light`, at most **two at a time**. The delegation message holds only pointers: ticket number, spec issue, integration branch, and the commit co-author line (subagents do not receive it otherwise).
- **Merger subagent (step 5):** none. The main session merges the ticket PR into the integration branch (`gh pr merge <n> --squash`), then comments on the ticket and closes it, so native blocking edges unblock the next tickets. GitHub closes issues only from PRs into the default branch. On a merge conflict, a fresh implementer resolves it.
- **Integration PR (steps 3 and 8):** a draft PR into `main` that closes the spec issue, listing every ticket. The owner merges it.
- **Cleanup (step 9):** `git worktree prune` and delete leftover local `worktree-agent-*` and ticket branches.

Never use the general-purpose agent for these jobs, and prefer `explorer` over the built-in Explore (which runs on Opus) for lookups. A subagent cannot spawn further subagents unless its tools include Agent; none of these do.

The session's own effort changes only by the owner typing `/effort`. The agent says "switch to `/effort high`" before a decision on gates, scoring rules or ADRs, or after two failed attempts at the same bug, and "back to `/effort medium`" when that is done. `xhigh` and `max` are not used routinely. If Sonnet tickets keep failing CI or need rework, move that kind of ticket back to Opus.

## Rules

- The owner decides: grilling answers, spec approval, merging code into `main`, gates, scoring rules and claims, ADRs, money, contacting people.
- The agent pushes any branch except `main` and merges `docs/*` and `chore/*` PRs after CI is green (enforced by a local hook and branch protection). No force push.
- The system under test never reads world data, the answer key or baselines (`tests/test_isolation.py`); prompt examples never come from TP-201.
- No `noqa`, skip, `pyright: ignore` or loosened tolerance without a written reason. Answer-key changes go in their own PR (design §10). New product packages go in pyright `strict`.
- A new task must pass: "if the result is A versus B, what do we build differently?" Ports only where a second implementation exists.
- Public repo: no private names, documents or plant details in code, issues, PRs or commits; the denylist checks all of them. A new worktree needs `.denylist.local` copied from the main checkout, or the denylist check fails.
